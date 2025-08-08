import asyncio
import feedparser
from typing import List
import json

from crawl4ai import AsyncWebCrawler, CrawlResult, BrowserConfig
from crawl4ai import LLMConfig, LLMExtractionStrategy, CrawlerRunConfig

from pathlib import Path
import os
import sys

KEYRING = os.environ["KEYRING"]
sys.path.insert(1, KEYRING)
from pol_app_deepseek import deepseek_key


def grab_links():
    rss_url = "https://moxie.foxnews.com/google-publisher/politics.xml"
    feed = feedparser.parse(rss_url)
    return [entry.link for entry in feed.entries]


async def parallel_exec(urls, prompt):
    extraction_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider="deepseek/deepseek-reasoner",
            api_token=deepseek_key,
        ),
        instruction=prompt,
        extract_type="schema",
        schema="{title: string, result: json}",
        overlap_rate=0.05,
        # schema="{title: string, url: string, comments: int}",
        # extra_args={
        #     "temperature": 0.0,
        #     "max_tokens": 4096,
        # },
        verbose=True,
    )

    browser_config = BrowserConfig(
        headless=True,
        browser_type="firefox"
    )
    crawl_config = CrawlerRunConfig(extraction_strategy=extraction_strategy)
    async with AsyncWebCrawler(config=browser_config) as crawler:
        results: List[CrawlResult] = await crawler.arun_many(
            urls=urls,
            config=crawl_config
        )

    return results


async def single_exec(url, prompt):
    extraction_strategy = LLMExtractionStrategy(
        llm_config=LLMConfig(
            provider="deepseek/deepseek-chat",
            api_token=deepseek_key,
        ),
        instruction=prompt,
        #extract_type="schema",
        #schema="{title: string, text: string}",
        schema="{title: string, result: json}",
        # extra_args={
        #     "temperature": 0.0,
        #     "max_tokens": 4096,
        # },
        verbose=True,
        # chunk_token_threshold=2000,
        # apply_chunking=False
        overlap_rate=0.05
    )

    browser_config = BrowserConfig(
        headless=True,
        browser_type="firefox"
    )
    crawl_config = CrawlerRunConfig(extraction_strategy=extraction_strategy)
    async with AsyncWebCrawler(config=browser_config) as crawler:
        results: List[CrawlResult] = await crawler.arun(
            url=url,
            config=crawl_config
        )

    return results


if __name__ == "__main__":
    with open('./prompt.txt', 'r') as f:
        prompt = f.read()

    #prompt = "You are going to be given a news article, I want you to extract the article title and the body text that relates to the title."

    links = grab_links()
    #links = ["https://www.foxnews.com/politics/key-aide-irs-tea-party-targeting-controversy-put-leave-after-allegations-new-anti-gop-effort"]
    res = asyncio.run(parallel_exec(links, prompt))
    #res = asyncio.run(single_exec(links[0], prompt))

    for i, result in enumerate(res):
        fname = f"{i}.json"

        # Try converting Jstring into object?
        content_json = json.loads(result.extracted_content)

        with open(f"./outputs/{fname}", "w+") as f:
            f.write(f'{result.url}\n\nResult:\n')
            json.dump(content_json, f, indent=2)
            f.write('\n\n')
            # f.write(f"Raw result:\n")
            # f.write(result)