import openai
import os
from dotenv import load_dotenv
from agent.SQLInjector import SQLInjector
from agent.XSSInjector import XSSInjector 
import asyncio
from playwright.async_api import async_playwright

async def main():
    # Load environment variables
    load_dotenv()
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

    openai.api_key = OPENAI_API_KEY
    
    print("\nPlease enter a URL for me to hack")
    await asyncio.sleep(0.5)

    url = input('\nURL: ')

    print("\nSelect injection type:")
    print("1. SQL Injection")
    print("2. XSS Injection")
    
    injection_type = input("\nChoose 1 or 2: ")

    async with async_playwright() as playwright:
        if injection_type == "1":
            # SQL Injection
            sql_injector = SQLInjector(base_url=url)
            await sql_injector.startup(playwright)
            await sql_injector.trial()
            await asyncio.sleep(0.5)
            input('\nClick enter to shut down the browser: ')
            await sql_injector.shutDown()

        elif injection_type == "2":
            # XSS Injection
            xss_injector = XSSInjector(base_url=url)
            await xss_injector.startup(playwright)
            await xss_injector.trial()
            await asyncio.sleep(0.5)
            input('\nClick enter to shut down the browser: ')
            await xss_injector.shutDown()

        else:
            print("\nInvalid option. Please choose either 1 or 2.")

if __name__ == '__main__':
    asyncio.run(main())
