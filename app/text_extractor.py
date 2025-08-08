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

# NOTE: Current thought is by separating text extraction vs claim extraction is to limit input tokens
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
        }[source_type]
    

    def run_async_handler(self, handler, entry):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(handler(entry))
        loop.close()
        return
    

    #NOTE: Depending on Crawl4AI to properly index chunks isn't reliable
    async def handle_news_article(self, entry):
        urls = entry['urls']

        logger.info("Started News Article Handler for...")
        for url in urls:
            logger.info(f"\t{url}")

        prompt = "\
        You are given the webpage for a text based News article. I want you to grab the \
        title of the article along with its content (stored into body_text). Ignore any \
        advertisements, captions, or anything else not related to what the article is about.\
        "
        extraction_strategy = LLMExtractionStrategy(
            llm_config=LLMConfig(
                provider="deepseek/deepseek-chat",
                api_token=os.getenv('DEEP_KEY'),
            ),
            instruction=prompt,
            extract_type="schema",
            schema="{url: string, title: string, body_text: string}",
            #overlap_rate=0.05,
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

        for result in results:
            res_json = json.loads(result.extracted_content)
            self.output_queue.put(res_json)
        return