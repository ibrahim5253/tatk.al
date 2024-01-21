#!/usr/bin/env python
# coding: utf-8

# In[236]:


import logging
import subprocess
import sys
import time
import pickle
import os.path
import time
import json
import traceback
import argparse
import logging

logging.basicConfig(
    format='%(asctime)s %(message)s',
    datefmt='%m/%d/%Y %I:%M:%S %p %z',
    filename='irctc.log',
    encoding='utf-8',
    level=logging.INFO)
logging.getLogger().addHandler(logging.StreamHandler())

from io import BytesIO
from datetime import date, timedelta, datetime
from pathlib import Path

from selenium.webdriver.chrome.service import Service
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys

import requests


work_dir = Path(sys.argv[0]).parent
cred_dir = work_dir / 'creds'

with open(cred_dir / 'openai_key.json') as f:
    api_key = json.load(f)

def solve_captcha(base64_image):
    headers = {
      "Content-Type": "application/json",
      "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
      "model": "gpt-4-vision-preview",
      "messages": [
        {
          "role": "user",
          "content": [
            {
              "type": "text",
              "text": "Solve the text captcha in this image. Respond only with the result. Nothing else."
            },
            {
              "type": "image_url",
              "image_url": {
                "url": base64_image
              }
            }
          ]
        }
      ],
      "max_tokens": 300
    }
    
    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
    logging.info(f'openai response: {response.json()}')

    return response.json()['choices'][0]['message']['content']

parser = argparse.ArgumentParser()
parser.add_argument('-d', "--dryrun", help="dry run; stop before payment",
                                        action="store_true")
parser.add_argument('-n', "--noautocaptcha", help="dont try to solve captcha",
                                        action="store_true")
parser.add_argument('-a', "--auto", help="autopilot mode; non-interactive",
                                        action="store_true")
args = parser.parse_args()

default_wait = 5 # secs

with open(cred_dir / 'journey.json') as f:
    journey = json.load(f)

with open(cred_dir / 'card.json') as f:
    card = json.load(f)

if 'date' not in journey:
    d = date.today() + timedelta(days=1)
    journey['date'] = d.strftime('%d/%m/%Y')

with open(cred_dir / 'login.json') as f:
    login = json.load(f)

dryrun = args.dryrun
autocaptcha = not args.noautocaptcha
if dryrun:
    print('this is a dry run. will stop at the final step')
if not autocaptcha:
    print('auto captcha disabled.')

with open('config.json') as f:
    service = Service(executable_path=json.load(f)['chrome_driver'])

chrome_options = Options()
chrome_options.add_argument("--window-size=1920,1080")
# if args.auto:
#    chrome_options.add_argument("--headless=new")
driver = webdriver.Chrome(service=service, options=chrome_options)
driver.implicitly_wait(default_wait)

def js_click(elem):
    driver.execute_script("arguments[0].click();", elem)

def wait_to_load():
    driver.implicitly_wait(0)
    while True:
        time.sleep(0.5)
        try:
            driver.find_element(By.CSS_SELECTOR, '.my-loading')
            continue
        except:
            break
    driver.implicitly_wait(default_wait)

def login_and_search():
    driver.get('https://www.irctc.co.in/')
    js_click(
        driver.find_element(By.CSS_SELECTOR, 'a[aria-label="Click here to Login in application"]')
    )
    driver.find_element(By.CSS_SELECTOR, 'input[formcontrolname="userid"]').send_keys(login['id'])
    driver.find_element(By.CSS_SELECTOR, 'input[formcontrolname="password"]').send_keys(login['password'])

    captchaResp = None
    while True:
        captcha = driver.find_element(By.CSS_SELECTOR, 'app-captcha img.captcha-img')
        captchaImg = captcha.get_attribute('src')
        if args.auto or (autocaptcha and captchaResp is None):
            captchaResp = solve_captcha(captchaImg)
            print('captcha guess: ', captchaResp)
        else:
            captchaResp = input('enter captcha here')

        driver.find_element(By.CSS_SELECTOR, 'input[formcontrolname="captcha"]').send_keys(captchaResp)
        # fixme may throw a stale reference exception
        driver.execute_script('arguments[0].removeAttribute("src");', captcha)
        js_click(
            driver.find_element(By.CSS_SELECTOR, "app-login button[type='submit'].search_btn.train_Search")
        )
        wait_to_load()
        invalidCaptcha = driver.find_element(
            By.XPATH,
            "//*[./img[contains(@class, captcha-img) "
                "and (contains(@src, 'data:image/jpg'))] "
            "or @aria-label='Click here Logout from application']")
        if 'Logout' not in invalidCaptcha.get_attribute('innerHTML'):
            logging.warning('captcha failed')
            continue
        else:
            break

    # Search trains

    for place, sel in zip((journey["from"], journey["to"]), ('pr_id_1_list', 'pr_id_2_list')):
        elem = driver.find_element(By.CSS_SELECTOR, f'input[aria-controls="{sel}"]')
        elem.clear()
        elem.send_keys(place['code'])
        js_click(
            driver.find_element(By.XPATH,
                                f"//*[@id='{sel}']/li[.//*[normalize-space(text())='{place['fullname']}'] and "
                                f".//*[normalize-space(text())='{place['state']}']]")
        )

    js_click(
        driver.find_element(By.CSS_SELECTOR, 'p-dropdown[formcontrolname="journeyQuota"] > div')
    )
    js_click(
        driver.find_element(By.CSS_SELECTOR, f'p-dropdownitem li[aria-label="{journey.get("quota", "TATKAL")}"]')
    )

    dt = driver.find_element(By.CSS_SELECTOR, "p-calendar input[type='text']")
    js_click(dt)
    for _ in range(10): dt.send_keys(Keys.RIGHT)
    for _ in range(10): dt.send_keys(Keys.BACKSPACE)
    dt.send_keys(journey['date'])

    # fixme may click not get registered?
    js_click(driver.find_element(By.CSS_SELECTOR, "button[type='submit'].search_btn.train_Search"))

    wait_to_load()


train = journey["train"]
cls   = journey["class"]
date  = datetime.strptime(
        journey["date"] , '%d/%m/%Y').strftime('%d %b')

def continue_booking(step):
    try:
        if step <= 0:
            logging.info('continuing to login and search')
            login_and_search()

        # Navigate to the train -> class

        if step <= 1:
            logging.info(f'navigating to {train} {cls}')
            js_click(
                driver.find_element(
                    By.XPATH,
                    f"//app-train-avl-enq[.//*[contains(text(), '{train}')]]"
                    f"//table//td[.//*[contains(text(), '{cls}')]]/div"
                )
            )
            wait_to_load()

        # Get availability for the date and start booking 

        if step <= 2:
            while True:
                logging.info(f'getting availability for {train} {cls} {date}')
                js_click(
                    driver.find_element(
                        By.XPATH,
                        f"//app-train-avl-enq//table//td"
                        f"[.//*[contains(text(), '{date}')] and .//*[contains(@class, 'AVAILABLE')"
                        + (" or contains(@class, 'WL') or contains(@class, 'REGRET')"
                           if journey.get('bookwl') else "")
                        + "]]/div"
                    )
                )
                
                bookBtn = driver.find_element(
                    By.XPATH,
                    f"//app-train-avl-enq[.//*[contains(text(), '{train}')]]"
                    f"//button[contains(text(), 'Book Now')]"
                )
                
                if 'disable-book' in bookBtn.get_attribute("class"):
                    logging.info('book now disabled. will retry after some time...')
                    time.sleep(10)
                    js_click(
                        driver.find_element(
                            By.XPATH,
                            f"//app-train-avl-enq[.//*[contains(text(), '{train}')]]"
                            f"//li[.//*[contains(text(), '{cls}')]]//div"
                        )
                    )
                    wait_to_load()
                    continue
                else:
                    js_click(bookBtn)
                    wait_to_load()
                    break

        # Passenger input

        if step <= 3:
            for i, px in enumerate(journey["psngs"]):
                if i > 3: break
                logging.info(f'adding passenger {px}')
                if len(driver.find_elements(By.CSS_SELECTOR, 'app-passenger')) < i+1:
                    time.sleep(0.1)
                    js_click(
                        driver.find_element(By.XPATH, "//*[contains(text(), '+ Add Passenger')]")
                    )
                    # wait to ensure new passenger row is added
                    _ = driver.find_element(By.XPATH, f"//*[count(.//app-passenger) > {i}]")

                appPx = driver.find_elements(By.CSS_SELECTOR, 'app-passenger')[i]

                pName = appPx\
                .find_element(By.CSS_SELECTOR, 'input[placeholder="Passenger Name"]')
                pName.clear()
                pName.send_keys(px['name'])
                
                pAge = appPx\
                .find_element(By.CSS_SELECTOR, 'input[formcontrolname="passengerAge"]')
                pAge.clear()
                pAge.send_keys(str(px['age']))
                
                Select(
                    appPx.find_element(By.CSS_SELECTOR, 'select[formcontrolname="passengerGender"]')
                ).select_by_visible_text(px['sex'])
                
                Select(
                    appPx.find_element(By.CSS_SELECTOR, 'select[formcontrolname="passengerBerthChoice"]')
                ).select_by_visible_text(px.get('pref', 'No Preference'))

                driver.implicitly_wait(0)
                if cateringOptions := appPx.find_elements(By.CSS_SELECTOR
                                                          , 'select[formcontrolname="passengerFoodChoice"]'):
                    Select(cateringOptions[0]).select_by_visible_text('No Food')
                driver.implicitly_wait(default_wait)   

            driver.implicitly_wait(0)
            if noInsurance := driver.find_elements(By.CSS_SELECTOR
                                                   , '#travelInsuranceOptedNo-0 > div'):
                js_click(noInsurance[0])
            driver.implicitly_wait(default_wait)

            continueBtn = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"].train_Search.btnDefault')
            js_click(continueBtn)

            wait_to_load()

        # Review booking

        if step <= 4:
            logging.info(f'reviewing booking')
            captchaResp = None
            while True:
                if args.auto or (autocaptcha and captchaResp is None):
                    captcha = driver.find_element(By.CSS_SELECTOR, 'app-captcha img.captcha-img').get_property('src')
                    captchaResp = solve_captcha(captcha)
                else:
                    captchaResp = input('enter captcha here: ')


                driver.find_element(By.CSS_SELECTOR, '#captcha').send_keys(captchaResp)
                js_click(
                    driver.find_element(By.CSS_SELECTOR, 'button[type="submit"].train_Search.btnDefault')
                )
                wait_to_load()
                
                captcha_failure = driver.find_element(
                    By.XPATH
                    , "//*[contains(text(), 'Multiple Payment Service') or "
                      "contains(text(), 'Invalid Captcha')]"
                )
                
                if 'Invalid Captcha' in captcha_failure.get_attribute('innerHTML'):
                    driver.execute_script(
                        "document.querySelector('p-toastitem').remove();"
                    )
                    logging.warning('captch failed')
                    continue
                else:
                    break

        # Payment Options

        if step <= 5:
            logging.info(f'selecting payment option')
            mpsBtn = driver.find_element(
                By.XPATH
                , "//*[contains(text(), 'Multiple Payment Service')]"
            )
            js_click(mpsBtn)
            js_click(driver.find_element(By.XPATH, "//*[contains(text(), 'International/Domestic Credit/Debit Cards')]"))
            js_click(driver.find_element(By.CSS_SELECTOR, "button.btn.btn-primary.hidden-xs.ng-star-inserted"))
            wait_to_load()

        # Payment Gateway

        if step <= 6:
            logging.info(f'on payment gateway')
            driver.implicitly_wait(30)
            card_num = driver.find_element(
                By.XPATH
                , '//*[@id="gl_card_number" or contains(text(), "Multiple Payment Service")]')
            if "Multiple Payment Service" in card_num.get_attribute('innerHTML'):
                logging.warning('redirected to payment options again')
                driver.implicitly_wait(default_wait)
                return continue_booking(5)
            card_num.send_keys(card['number'])
            driver.find_element(By.ID, 'gl_card_expiryDate').send_keys(card['exp'])
            driver.find_element(By.ID, 'gl_card_securityCode').send_keys(card['cvv'])
            driver.find_element(By.ID, 'gl_billing_addressPostalCode').send_keys(card['postal'])
            js_click(driver.find_element(By.ID, 'network_dcc_2'))
            js_click(driver.find_element(By.ID, 'continue_in_foreign_currency_button'))
            if not dryrun:
                js_click(driver.find_element(By.ID, 'card_paynow_button'))

    except:
        logging.exception('Error continuing booking')
        if args.auto:
            sys.exit(1)
        step = int(input('something went wrong. enter step to continue from (0: login, 1: select train, 2: get avail, 3: psgn input, 4: review, 5: pay options, 6: payment): '))
        driver.implicitly_wait(default_wait)
        continue_booking(step)

continue_booking(0)

if args.auto:
    sys.exit(0)

_ = input('Enter to quit')
