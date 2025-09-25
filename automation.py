import asyncio
import gspread
import re
from oauth2client.service_account import ServiceAccountCredentials
from playwright.async_api import async_playwright

# Globals to track progress
progress = {"running": False, "progress": 0, "total": 0, "error": None, "message": ""}


async def click_grader_grade(page, grader: str, grade: str) -> bool:
    try:
        popup = page.locator("div[data-testid='card-pops']").first
        await popup.scroll_into_view_if_needed()
        header = page.get_by_text(f"{grader} population", exact=True)
        if not await header.count():
            return False
        wrapper = header.locator("xpath=..")
        buttons = wrapper.locator("button")
        for i in range(await buttons.count()):
            btn = buttons.nth(i)
            text = (await btn.locator("span").first.text_content() or "").strip()
            if text == grade:
                await btn.click(timeout=2000)
                return True
        return False
    except:
        return False


async def fetch_prices(page, num_sales=4):
    prices = []
    blocks = page.locator("div.MuiTypography-body1.css-vxna0y")
    for i in range(await blocks.count()):
        try:
            text = await blocks.nth(i).locator("span[class*='css-16tlq5a']").inner_text()
            match = re.search(r"\$([0-9\s,\.]+)", text)
            if match:
                price = float(match.group(1).replace(",", "").replace(" ", ""))
                prices.append(price)
            if len(prices) >= num_sales:
                break
        except:
            continue
    return prices


async def process_rows_async(all_values, start_row, sheet, email, password):
    global progress
    progress["running"] = True
    progress["progress"] = 0
    progress["total"] = len(all_values) - (start_row - 1)
    progress["error"] = None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context()
            page = await context.new_page()

            for row in range(start_row - 1, len(all_values)):
                if not progress["running"]:
                    break

                rnum = row + 1
                try:
                    row_vals = all_values[row]
                    url = row_vals[5] if len(row_vals) > 5 else ""
                    grader = row_vals[6] if len(row_vals) > 6 else ""
                    fake_grade = row_vals[7] if len(row_vals) > 7 else ""
                    if not url or not grader or not fake_grade:
                        continue
                    grade = fake_grade[:2] if len(fake_grade) > 3 else fake_grade

                    await page.goto(url, timeout=30000)
                    await page.wait_for_timeout(2000)

                    # Click card button
                    try:
                        button = page.locator("button.MuiButtonBase-root.css-1ege7gw").first
                        await button.click()
                    except:
                        pass

                    # Select grader
                    success = await click_grader_grade(page, grader, grade)
                    if success:
                        prices = await fetch_prices(page, 4)
                        if prices:
                            avg = sum(prices) / len(prices)
                            for i, price in enumerate(prices[:4]):
                                sheet.update_cell(rnum, 12 + i, price)
                            sheet.update_cell(rnum, 16, avg)

                except Exception as e:
                    progress["error"] = str(e)

                progress["progress"] += 1

            await browser.close()
    except Exception as e:
        progress["error"] = str(e)

    progress["running"] = False
    progress["message"] = "Automation finished"


def run_automation(json_path, sheet_name, email, password, start_row=1):
    global progress
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
    client = gspread.authorize(creds)
    sheet = client.open(sheet_name).sheet1
    all_values = sheet.get_all_values()
    asyncio.run(process_rows_async(all_values, start_row, sheet, email, password))
