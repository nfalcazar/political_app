import asyncio
from crawl4ai import AsyncWebCrawler, CacheMode
from crawl4ai import CrawlerRunConfig, BrowserConfig
from crawl4ai import LLMConfig, LLMExtractionStrategy
from crawl4ai import MemoryAdaptiveDispatcher
from dotenv import load_dotenv
import inspect
import json
import logging
import logging.config
import multiprocessing as mp
import os
import time
from util.ContinuousExecutor import ContinuousExecutor

# NOTE: Current thought by separating text extraction vs claim extraction is to limit input tokens
#       into more expensive reasoning model (just text vs full page source)
logger = logging.getLogger(__name__)

class TextExtractor(mp.Process):
    def __init__(self, input_queue, output_queue, max_threads=10):
        super().__init__()
        load_dotenv(dotenv_path='./.env')
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.max_threads = max_threads

    
    def run(self):
        logging.debug("Started Run")
        thread_pool = ContinuousExecutor(
            max_workers=self.max_threads,
            poll_interval=10
        )

        while True:
            entry = self.input_queue.get()
            if entry is None:
                logger.info("Detected Shutdown sentinel - None.")
                break

            handler = self.get_handler(entry["source_type"])
            if inspect.iscoroutinefunction(handler):
                thread_pool.submit(self.run_async_handler, handler, entry)
            else:
                thread_pool.submit(handler, entry)

        # Wait for current links to be processed
        while thread_pool.has_jobs():
            time.sleep(5)
        thread_pool.shutdown(wait=True, cancel_futures=False)
        logging.info("Shutting down.")
        return
            

    def get_handler(self, source_type):
        return {
            "news_article": self.handle_news_article,
            "gen_text_source": self.handle_gen_text_source
        }[source_type]
    

    def run_async_handler(self, handler, entry):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(handler(entry))
        loop.close()
        return
    

    #NOTE: Depending on Crawl4AI to properly index chunks isn't reliable
    #TODO: Consider favoring threads vs parallel async to tie entries w/ results
    #   - Removes need to add url and date fields in schema
    #   - Assumes probably used perp or google cust search with has access to publish dates
    async def handle_news_article(self, entry):
        urls = entry['urls']

        logger.info("Started News Article Handler for...")
        for url in urls:
            logger.info(f"\t{url}")

        prompt = "\
        You are given the webpage for a text based News article. I want you to grab the \
        title of the article (stored in title), the date the article was publised in the format \
        'Fri, 08 Aug 2025 17:43:55 -0400' where -400 is the UTC offset (stored in published), \
        along with its content (stored into body_text). Ignore any advertisements, captions, or \
        anything else not related to what the article is about.\
        "
        extraction_strategy = LLMExtractionStrategy(
            llm_config=LLMConfig(
                provider="deepseek/deepseek-chat",
                api_token=os.getenv('DEEP_KEY'),
            ),
            instruction=prompt,
            extract_type="schema",
            schema="{url: string, title: string, published: string, body_text: string}",
            apply_chunking=False,
            verbose=False,
        )
        browser_config = BrowserConfig(
            headless=True,
            browser_type="firefox",
            verbose=False
        )
        config = CrawlerRunConfig(
            extraction_strategy=extraction_strategy,
            cache_mode=CacheMode.BYPASS, 
            verbose=False
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            result_container = await crawler.arun_many(urls=urls, config=config)
            results = []
            if isinstance(result_container, list):
                results = result_container
            else:
                async for res in result_container:
                    results.append(res)

        #NOTE: Assuming running w/ apply_chuncking=False produces single element lists
        for result in results:
            res_json = json.loads(result.extracted_content)
            self.output_queue.put(res_json[0])
        return
    

    async def handle_gen_text_source(self, entry):
        urls = entry['urls']
        if 'query' in entry.keys():
            query = entry['query']

        logger.info("Started News Article Handler for...")
        for url in urls:
            logger.info(f"\t{url}")

        prompt = "\
        You are given the webpage for a text based article and possibly a search query that grabbed that \
        article. I want you to grab the following if they exist: title of the article (stored in title), \
        the date the article was publised in the format 'Fri, 08 Aug 2025 17:43:55 -0400' where -400 is \
        the UTC offset (stored in published). I want you to grab the content (stored into body_text) that \
        relates to the original search query if given. Ignore any advertisements, captions, menus, buttons \
        or anything else not related to what the article or query is about.\
        "
        extraction_strategy = LLMExtractionStrategy(
            llm_config=LLMConfig(
                provider="deepseek/deepseek-chat",
                api_token=os.getenv('DEEP_KEY'),
            ),
            instruction=prompt,
            extract_type="schema",
            schema="{url: string, title: string, published: string, body_text: string}",
            apply_chunking=False,
            verbose=False,
        )
        browser_config = BrowserConfig(
            headless=True,
            browser_type="firefox",
            verbose=False
        )
        config = CrawlerRunConfig(
            extraction_strategy=extraction_strategy,
            cache_mode=CacheMode.BYPASS, 
            verbose=False
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            result_container = await crawler.arun_many(urls=urls, config=config)
            results = []
            if isinstance(result_container, list):
                results = result_container
            else:
                async for res in result_container:
                    results.append(res)

        #NOTE: Assuming running w/ apply_chuncking=False produces single element lists
        for result in results:
            res_json = json.loads(result.extracted_content)
            self.output_queue.put(res_json[0])
        return