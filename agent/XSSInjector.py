from typing import Optional
from playwright.async_api import async_playwright, Playwright
from bs4 import BeautifulSoup
import re
import asyncio
from utils.spinner import Spinner
from utils.gpt import gpt
from utils.file_io import save_file

class XSSInjector:
    """
    LLM agent that tries to find XSS vulnerabilities on a website.
    """
    def __init__(self, base_url: str) -> None:
        """
        Constructor

        Parameters:
        base_url (str): URL to the homepage of the target website
        """
        self.baseURL = base_url
        self.urlsVisited: set[str] = set()

        self.browser = None
        self.page = None

    async def startup(self, playwright: Playwright) -> None:
        """
        Launch Chromium and open a new page
        """
        chromium = playwright.chromium
        self.browser = await chromium.launch(headless=False)
        self.page = await self.browser.new_page()
        await self.page.goto(self.baseURL)
        await self.page.wait_for_load_state('domcontentloaded')

    async def trial(self) -> bool:
        """
        Try XSS injection on the target website.
        """
        stack: list[str] = [self.page.url]

        while stack:
            url = stack.pop()

            if url in self.urlsVisited:
                continue

            print("Current URL: ", url)
            self.urlsVisited.add(url)

            all_xss_payloads = ""
            for num_trials in range(5):
                print(f"Iteration {num_trials}")

                await self.page.goto(url)
                await self.page.wait_for_load_state('domcontentloaded')

                html = await self.readHTML()

                has_input, has_link, has_button = checkHTML(html)

                await asyncio.sleep(0.5)

                if not has_input and not has_link and not has_button:
                    break

                if has_link and num_trials == 0:
                    links = self.checkLinks(html)
                    stack += links

                if not has_input:
                    break

                plan = await self.makePlan(html, failed_xss_payloads=all_xss_payloads)

                if not plan or not plan:
                    break

                func_str = await self.act(html, plan)

                await asyncio.sleep(0.5)

                newHtml = await self.readHTML()

                if await self.checkSuccess(newHtml, html):
                    print("XSS injection successful!")
                    return True

                xss_payloads = await self.extractXSSPayloads(function=func_str)
                all_xss_payloads += xss_payloads

        print("XSS injection failed!")
        return False

    async def readHTML(self, save_html=False) -> str:
        """
        Helper function to read the HTML of the webpage currently held by this instance

        Returns:
        str: string of the HTML content
        """
        html = await self.page.content()

        if not html:
            raise Exception(f'Error fetching the webpage. Please check the network condition or try again.')

        if save_html:
            save_file('test.html', html)

        html = preprocessHTML(html)
        return html

    async def makePlan(self, html: str, failed_xss_payloads: Optional[str]=None) -> list[str]:
        """
        Make a plan for XSS injection. E.g., which fields to inject into, which buttons to click.

        Parameters:
        html (str): HTML content of the webpage currently worked on

        Returns:
        list[str]: instructions for each step
        """
        with Spinner("Writing a plan for XSS injection..."):
            prompt = ("I am learning website security, and I want to practice XSS injection on a sandbox website which is deliberately made vulnerable, "
                    "this is one of its webpages. Can you list the actions I need to do on this page? "
                    "ONLY INCLUDE ACTIONS I NEED TO DO WITH MY KEYBOARD AND MOUSE. "
                    "Only interact with elements currently on this page.\n\n"
                    f"```html\n{html}\n```\n\n"
                    f"Here are the XSS payloads that failed previously:\n{failed_xss_payloads}\n\n")
            
            prompt += "If certain payloads failed previously, try different payloads before trying others." if failed_xss_payloads else ""

            response = gpt(system_msg="", user_msg=prompt)

        lines = response.split('\n')
        plan = [line for line in lines if re.match(r'^\s*-?\d+', line)]

        print("Here is my plan:")
        print('\n'.join(plan))

        return plan

    async def act(self, html: str, plan: str) -> str:
        """
        Make the agent act based on the instruction provided

        Parameters:
        html (str): HTML of the webpage currently worked on
        plan (str): plan for XSS injection

        Returns:
        str: The function executed
        """
        filtered_plan = [instruction for instruction in plan if "browser" not in instruction.lower() and "window" not in instruction.lower() and "navigate" not in instruction.lower()]

        plan_str = '\n'.join(filtered_plan) if filtered_plan else "None"

        prompt = ("I am learning website security, and I want to practice XSS injection on a sandbox website which is deliberately made vulnerable. "
        "Here is HTML for that webpage:\n\n"
        f"```html\n{html}\n```\n\n"
        "I would open the webpage in Chromium and navigate to the sandbox website when initializing an instance of this class:\n\n"
        """```python
class XSSInjector:
    async def __init__(self, url) -> None:
        with sync_playwright() as p:
            self.browser = await p.chromium.launch(headless=False)
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()
            await self.page.goto(url)
            await self.page.wait_for_load_state('domcontentloaded')
```"""
        "\n\nCan you help me write a Python function `async def func(self) -> None` corresponding to the following action:\n\n"
        f"{plan_str}\n\n"
        "Remember to use `self.browser` and `self.page` instead of `browser` and `page`. "
        "This function shouldn't have any return.")

        with Spinner("Writing code for this step..."):
            response = gpt(system_msg="", user_msg=prompt)

        func_str = extract_function(source_code=response, function_name="func")
        try:
            exec(func_str, globals(), locals())
            import types
            self.func = types.MethodType(locals()['func'], self)
            await asyncio.wait_for(self.func(), timeout=15.0)
        except Exception as err:
            if isinstance(err, asyncio.TimeoutError): 
                print("This program I wrote doesn't finish in 15 seconds")
            else:
                print(err)

        return func_str

    async def extractXSSPayloads(self, function: str) -> str:
        """
        Extract all the XSS payloads used in this function

        Parameters:
        function (str): string of Python script that may have an XSS action

        Returns:
        str: Concatenated XSS payloads
        """
        prompt = ("I am learning website security, and I want to practice XSS injection on a sandbox website which is deliberately made vulnerable, "
         "and I have attempted XSS injection with the following Python script."
         f"```python\n{function}\n```\n\n"
         "Can you list the XSS payloads I used? Wrap the payload between ```xss and ```. If there is no XSS injection, answer NONE")

        with Spinner("Extracting XSS payloads used in this trial..."):
            response = gpt(system_msg="", user_msg=prompt)
        
        if "NONE" in response:
            return ""
        
        pattern = r'```xss(.*?)```'
        matches = re.findall(pattern, response, re.DOTALL)
        matches = [match.strip() for match in matches]
        return '\n'.join(matches) + '\n'

    async def checkSuccess(self, newHtml: str, prevHtml: str) -> bool:
        """
        Check whether XSS injection succeed by comparing the current HTML and previous HTML

        Parameters:
        newHtml (str): HTML of the webpage after a series of actions
        prevHtml (str): HTML of the webpage before the agent act on it
        """
        with Spinner("check whether this XSS injection is successful..."):

            prompt = ("I am learning website security, and I want to practice XSS injection to a sandbox website which is deliberately made vulnerable, "
                    "and I have attempted a XSS injection. Comparing the webpage after I did this trial and before that, "
                    "can you tell whether this XSS injection is successful or not?\n\n"
                    "HTML of the webpage before trial:\n\n"
                    f"```html\n{prevHtml}\n```\n\n"
                    "HTML of the webpage after trial:\n\n"
                    f"```html\n{newHtml}\n```\n\n"
                    "Answer YES or NO")
            
            response = gpt(system_msg="", user_msg=prompt)

            if response == "YES":
                return True
            else:
                return False
        
    
    def checkLinks(self, html: str) -> list[str]:
        """
        Find the links on the page worth checking

        Parameters:
        html (str): HTML content of the webpage currently worked on
        
        Returns:
        list[str]: list of the links worth checking
        """
        soup = BeautifulSoup(html, "html.parser")
        anchor_tags = soup.find_all('a')
        hrefs = [tag.get('href') for tag in anchor_tags if tag.get('href')]
        valid_hrefs = []
        for href in hrefs:
            if href.startswith(self.baseURL) or href.startswith('/'):
                if href.startswith('/'):
                    if self.baseURL.endswith('/'):
                        valid_hrefs.append(self.baseURL + href[1:])
                    else:
                        valid_hrefs.append(self.baseURL + href)
                else:
                    valid_hrefs.append(href)
        print("Here are the links I think worth trying:", valid_hrefs)
        return valid_hrefs
    

    async def shutDown(self):
        await self.browser.close()


### Helper Functions ###

def preprocessHTML(html: str) -> str:
        """
        preprocess the HTML to remove script style and head, to make HTML easier for GPT to read

        Parameters:
        html (str): string of HTML
        
        Returns:
        str: HTML after preprocessing
        """
        soup = BeautifulSoup(
            "".join(s.strip() for s in html.split("\n")),
            "html.parser",
        )

        # remove scripts and styles
        for s in soup.select("script"):
            s.extract()
        for s in soup.select("style"):
            s.extract()

        # remove head if there is one
        head = soup.find("head")
        if head:
            head.extract()

        # Find all tags with a class attribute
        for tag in soup.find_all(class_=True):
            del tag['class']  # Remove the class attribute

        return soup.body.prettify()


def checkHTML(html: str) -> tuple[bool]:
        """
        Check if there is input field, anchor tag, or button in the given HTML code

        Parameters:
        html (str): string of HTML
        
        Returns:
        tuple[bool]: Whether there are input fields, anchor tags, or buttons
        """
        soup = BeautifulSoup(html, "html.parser")

        input_elements = soup.find_all('input')
        anchor_tags = soup.find_all('a')
        buttons = soup.find_all('button')

        return bool(input_elements), bool(anchor_tags), bool(buttons)


def extract_function(source_code, function_name) -> Optional[str]:
    """
    Helper function to extract a specified function from a string of code.

    Parameters:
    source_code (str): string of code
    function_name (str): name of the function of interest
    
    Returns:
    Optional[str]: the object function (if exist)
    """
    pattern = rf"async def {function_name}\(.*\) -> None:([\s\S]+?)^\S"
    match = re.search(pattern, source_code, re.MULTILINE)

    if match:
        function_code = f"async def {function_name}(self):" + match.group(1)
        function_code = function_code.strip()
        return function_code
    else:
        pattern = rf"async def {function_name}\(.*\):([\s\S]+?)^\S"
        match = re.search(pattern, source_code, re.MULTILINE)
        if match:
            function_code = f"async def {function_name}(self):" + match.group(1)
            function_code = function_code.strip()
            return function_code
        else:
            return None