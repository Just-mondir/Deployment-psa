import os
import json
import re
import asyncio
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from playwright.async_api import async_playwright

# Global progress tracking
progress = {
    "running": False,
    "progress": 0,
    "total": 0,
    "error": None,
    "message": ""
}

# Constant credentials
EMAIL = "likepeas@gmail.com"
PASSWORD = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

async def click_grader_grade(page, grader: str, grade: str) -> bool:
    """Click the '<grader> population' button matching `grade` exactly."""
    try:
        # Wait for popup to be available
        progress["message"] = f"Looking for grader {grader} with grade {grade}..."
        popup = page.locator("div[data-testid='card-pops']").first
        
        try:
            await popup.wait_for(state="visible", timeout=5000)
        except:
            progress["message"] = "Popup not found, might need to click the card button again"
            # Try clicking the card button again
            try:
                button = page.locator("button.MuiButtonBase-root.css-1ege7gw").first
                await button.click()
                await page.wait_for_timeout(2000)
            except:
                return False

        await popup.scroll_into_view_if_needed()
        await page.wait_for_timeout(900)

        header = page.get_by_text(f"{grader} population", exact=True)
        if not await header.count():
            progress["message"] = f"Could not find '{grader} population' text"
            return False

        wrapper = header.locator("xpath=..")
        buttons = wrapper.locator("button")

        button_count = await buttons.count()
        for i in range(button_count):
            btn = buttons.nth(i)
            grade_span = btn.locator("span").first
            text = await grade_span.text_content()
            text = text.strip() if text else ""

            if text == grade:
                await btn.scroll_into_view_if_needed()
                await btn.click(timeout=2000)
                await page.wait_for_timeout(500)
                return True

        progress["message"] = f"Grade {grade} not found for {grader}"
        return False
    except Exception as e:
        progress["message"] = f"Error selecting {grader} {grade}: {e}"
        return False

async def fetch_prices(page, num_sales=4):
    await page.wait_for_timeout(3000)

    prices = []
    blocks = page.locator("div.MuiTypography-body1.css-vxna0y")

    block_count = await blocks.count()
    for i in range(block_count):
        try:
            price_span = blocks.nth(i).locator("span[class*='css-16tlq5a']")
            price_text = await price_span.inner_text()
            match = re.search(r"\$([0-9\s,\.]+)", price_text)
            if match:
                price_str = match.group(1).replace(" ", "").replace("\u202f", "").replace(",", "")
                price = float(price_str)
                prices.append(price)
            if len(prices) >= num_sales:
                break
        except Exception as e:
            progress["message"] = f"Error fetching price {i+1}: {e}"
            continue
    return prices

async def perform_login_if_needed(page) -> bool:
    try:
        login_btn = page.locator("button:has-text('Log in')").first
        if await login_btn.count():
            await login_btn.click()
            await page.wait_for_timeout(1000)

            # Email input
            email_selectors = [
                "input[type='email']",
                "input[name='email']",
                "input#email",
                "input[name='username']",
                "input[type='text']"
            ]
            email_input = None
            for sel in email_selectors:
                el = page.locator(sel).first
                if await el.count():
                    email_input = el
                    break

            if email_input is None:
                possible = page.locator("input")
                for i in range(await possible.count()):
                    inp = possible.nth(i)
                    try:
                        placeholder = (await inp.get_attribute("placeholder")) or ""
                        aria = (await inp.get_attribute("aria-label")) or ""
                        name = (await inp.get_attribute("name")) or ""
                        if "@" in placeholder or "email" in placeholder.lower() or "email" in aria.lower() or "email" in name.lower():
                            email_input = inp
                            break
                    except:
                        continue

            if email_input:
                await email_input.fill(EMAIL)
                await page.wait_for_timeout(300)
            else:
                progress["message"] = "Could not locate email input"
                return False

            # Password input
            password_selectors = [
                "input[type='password']",
                "input[name='password']",
                "input#password"
            ]
            password_input = None
            for sel in password_selectors:
                el = page.locator(sel).first
                if await el.count():
                    password_input = el
                    break

            if password_input is None:
                possible = page.locator("input")
                for i in range(await possible.count()):
                    inp = possible.nth(i)
                    try:
                        itype = (await inp.get_attribute("type")) or ""
                        name = (await inp.get_attribute("name")) or ""
                        aria = (await inp.get_attribute("aria-label")) or ""
                        if "password" in itype.lower() or "pass" in name.lower() or "password" in aria.lower():
                            password_input = inp
                            break
                    except:
                        continue

            if password_input:
                await password_input.fill(PASSWORD)
                await page.wait_for_timeout(300)
            else:
                progress["message"] = "Could not locate password input"
                return False

            # Submit
            submitted = False
            submit_btn = page.locator(
                "button:has-text('Log in'), button:has-text('Log In'), button:has-text('Sign in'), button:has-text('Sign In'), button[type='submit']"
            ).last
            if await submit_btn.count():
                try:
                    await submit_btn.click()
                    submitted = True
                except:
                    submitted = False

            if not submitted and password_input:
                try:
                    await password_input.press("Enter")
                    submitted = True
                except:
                    submitted = False

            if submitted:
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except:
                    pass
                await page.wait_for_timeout(2000)
                return True
            else:
                progress["message"] = "Login not submitted (no submit button found)"
                return False
        else:
            return True
    except Exception as e:
        progress["message"] = f"Error during login: {e}"
        return False

async def process_rows_async(all_values, start_row, sheet):
    global progress
    progress["running"] = True
    progress["progress"] = 0
    progress["total"] = len(all_values) - (start_row - 1)
    progress["error"] = None
    progress["message"] = f"Starting automation with {len(all_values)} total rows, starting from row {start_row}..."
    
    # Validate input data
    if start_row < 1 or start_row > len(all_values):
        progress["error"] = f"Invalid start row: {start_row}"
        progress["running"] = False
        return
        
    if len(all_values) < 2:  # Need at least header + 1 data row
        progress["error"] = "Sheet must contain at least 2 rows (header + data)"
        progress["running"] = False
        return

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/121.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            
            # Track if we've done the initial login
            is_first_card = True
            logged_in = False

            for row in range(start_row - 1, len(all_values)):
                if not progress["running"]:
                    progress["message"] = "Automation stopped by user"
                    break

                rnum = row + 1
                try:
                    row_vals = all_values[row]
                    url = row_vals[4] if len(row_vals) > 4 else ""        # Column E
                    grader = row_vals[1] if len(row_vals) > 1 else ""     # Column B
                    fake_grade = row_vals[2] if len(row_vals) > 2 else "" # Column C

                    if not url or not grader or not fake_grade:
                        progress["message"] = f"Skipping row {rnum}: Missing required data (url: {url}, grader: {grader}, grade: {fake_grade})"
                        progress["progress"] += 1
                        continue

                    grade = fake_grade[:2] if len(fake_grade) > 3 else fake_grade
                    progress["message"] = f"Processing row {rnum}: {grader} {grade} (URL: {url})"

                    try:
                        # Navigation with debug info
                        progress["message"] = f"Navigating to card URL for row {rnum}..."
                        await page.goto(url, timeout=30000)
                        await page.wait_for_timeout(2000)
                        
                        # Try to click card button with retries and debug info
                        max_retries = 3
                        button_clicked = False
                        
                        for retry in range(max_retries):
                            try:
                                progress["message"] = f"Attempting to click card button (attempt {retry + 1}/{max_retries})..."
                                button = page.locator("button.MuiButtonBase-root.css-1ege7gw").first
                                
                                # Wait for button to be visible
                                await button.wait_for(state="visible", timeout=5000)
                                
                                # Try to scroll to button
                                await button.scroll_into_view_if_needed()
                                await page.wait_for_timeout(1000)
                                
                                # Click the button
                                await button.click()
                                await page.wait_for_timeout(2000)
                                button_clicked = True
                                progress["message"] = f"Successfully clicked card button on row {rnum}"
                                break
                            except Exception as click_error:
                                progress["message"] = f"Button click attempt {retry + 1} failed: {str(click_error)}"
                                await page.wait_for_timeout(1000)
                        
                        if not button_clicked:
                            progress["message"] = f"⚠️ Failed to click card button after {max_retries} attempts on row {rnum}. Skipping to next row."
                            progress["progress"] += 1
                            continue

                        # Only handle login for the first card
                        if is_first_card:
                            progress["message"] = "Performing initial login..."
                            if await perform_login_if_needed(page):
                                logged_in = True
                                progress["message"] = "Successfully logged in. Processing cards..."
                            else:
                                progress["error"] = "Failed to perform initial login"
                                return
                            
                            # After login, click the card button again with debug
                            try:
                                progress["message"] = "Re-clicking card button after login..."
                                await button.click()
                                await page.wait_for_timeout(2000)
                            except Exception as post_login_error:
                                progress["message"] = f"Failed to click button after login: {str(post_login_error)}. Skipping row."
                                progress["progress"] += 1
                                continue
                            
                            is_first_card = False
                            
                    except Exception as e:
                        progress["message"] = f"Navigation/button error for row {rnum}: {str(e)}"
                        if is_first_card:  # If we failed on first card, stop entirely
                            progress["error"] = "Failed to process first card and login"
                            return
                        continue

                    # Select grader and grade
                    success = await click_grader_grade(page, grader, grade)
                    if success:
                        prices = await fetch_prices(page, 4)
                        if prices:
                            avg = sum(prices) / len(prices)
                            for i, price in enumerate(prices[:4]):
                                sheet.update_cell(rnum, 5 + i, price)    # Start from column F (index 5)
                            sheet.update_cell(rnum, 9, avg)              # Column J (index 9) for average
                            progress["message"] = f"Updated row {rnum} with prices and average"
                        else:
                            progress["message"] = f"No prices found for row {rnum}"
                    else:
                        progress["message"] = f"Could not select grader/grade for row {rnum}"

                    progress["progress"] += 1
                    await page.wait_for_timeout(1200)

                except Exception as e:
                    progress["error"] = str(e)
                    progress["message"] = f"Error processing row {rnum}: {e}"
                    continue

            await browser.close()
            progress["message"] = "Automation completed"
            progress["running"] = False

    except Exception as e:
        progress["error"] = str(e)
        progress["message"] = f"Critical error: {e}"
        progress["running"] = False

def run_automation(json_path, sheet_name, email=EMAIL, password=PASSWORD):
    """Main entry point for the automation"""
    global progress, EMAIL, PASSWORD
    
    # Update credentials if provided (but fallback to constants if not)
    if email != EMAIL:
        EMAIL = email
    if password != PASSWORD:
        PASSWORD = password

    try:
        # Reset progress state
        progress.update({
            "running": True,
            "progress": 0,
            "total": 0,
            "error": None,
            "message": "Initializing..."
        })

        # Verify the JSON file exists
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"JSON credentials file not found: {json_path}")

        # Setup Google Sheets
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        progress["message"] = "Loading credentials..."
        
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
            client = gspread.authorize(creds)
            sheet = client.open(sheet_name).sheet1
        except Exception as e:
            raise Exception(f"Failed to connect to Google Sheets: {str(e)}")

        progress["message"] = "Reading sheet data..."
        all_values = sheet.get_all_values()
        
        if not all_values:
            raise Exception("Sheet is empty")

        # Set initial progress state
        total_rows = len(all_values) - 1  # Subtract 1 to account for header row
        if total_rows <= 0:
            raise Exception("No data rows found in sheet")

        progress.update({
            "total": total_rows,
            "progress": 0,
            "message": f"Connected to sheet '{sheet_name}'. Found {total_rows} rows to process."
        })

        # Run the async processing - always start from row 2 to skip header
        asyncio.run(process_rows_async(all_values, 2, sheet))

    except Exception as e:
        progress["error"] = str(e)
        progress["message"] = f"Setup error: {e}"
        progress["running"] = False