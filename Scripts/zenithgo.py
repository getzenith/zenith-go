#!/usr/bin/python

# Zenith Go Firmware
# © 2024 Zenith - All Rights Reserved
FIRMWARE_VERSION = "20240225.1"

# Import configuration
from config import FTP_USERNAME, FTP_PASSWORD, FTP_ADDRESS, OPENAI_API_KEY

import RPi.GPIO as GPIO
from ftplib import FTP
from picamera import PiCamera
from PIL import Image
import time
import os
import base64
import requests
import json
import re
import threading

# Global Constants
CAMERA_BTN = 22
RED_LED = 15
GREEN_LED = 13
BLUE_LED = 11

# FTP Info
ftp_username = FTP_USERNAME
ftp_passwd = FTP_PASSWORD
ftp_addr = FTP_ADDRESS

# Initialize camera
camera = PiCamera()
camera.resolution = (1280, 720)

# Button state
btn_press = False

# GPIO Setup
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
GPIO.setup(CAMERA_BTN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# Initialize LED PWM
pwm_led = []
for led in [RED_LED, GREEN_LED, BLUE_LED]:
    GPIO.setup(led, GPIO.OUT)
    pwm_led.append(GPIO.PWM(led, 100))
    pwm_led[-1].start(0)


def toggle_led(led, duty_cycle=0):
    led.ChangeDutyCycle(duty_cycle)


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def extract_json_text(text):
    pattern = r"\{.*\}"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        json_text = match.group()
        json_obj = json.loads(json_text)
        return json_obj
    else:
        return None


# Define a function for the LED to blink rapidly
def rapid_blink(led):
    for _ in range(5):  # Adjust the number of blinks as needed
        led.ChangeDutyCycle(25)  # Turn on the LED
        time.sleep(0.1)  # Adjust the blink rate as needed
        led.ChangeDutyCycle(0)  # Turn off the LED
        time.sleep(0.1)  # Adjust the blink rate as needed


def analyze_image(image_path):
    print("\033[33m[+] Sending image to OpenAI for analysis...\033[0m")
    api_key = OPENAI_API_KEY

    question = 'Does the attached image depict a potential hazard such as fallen powerline, fallen tree, house collsape or other hazard? Answer in a JSON string format with the ' \
               'fields "answer" with either "yes" or "no" only and the field "reason" with a brief explanation for' \
               ' your answer. Do not include any further text, just the JSON string please.'

    base64_image = encode_image(image_path)

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
                        "text": question
                    },
                    {
                        "type": "image_url",
                        "image_url": f"data:image/jpeg;base64,{base64_image}"
                    }
                ]
            }
        ],
        "max_tokens": 100
    }

    try:
        # Start a thread to make the LED blink
        threading.Thread(target=rapid_blink, args=(pwm_led[2],)).start()
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response_json = response.json()
        print("\033[33m[+] Received response from OpenAI:\033[0m")
        print(response_json)
        result = extract_json_text(response_json['choices'][0]['message']['content'])
        return result
    except Exception as e:
        print("\033[31m[!] Error analyzing image:", e, "\033[0m")
        toggle_led(pwm_led[0], 25)  # Turn on red LED in case of error
        return None


def grab_and_upload():
    print("\033[33m[+] Getting photo.\033[0m")
    

    pic_name = 'latest_image.jpg'
    camera.capture(pic_name)
    toggle_led(pwm_led[2], 25)  # Turn on blue LED
    img = Image.open(pic_name)
    rotated_img = img.rotate(180)
    rotated_img.save(pic_name)

    toggle_led(pwm_led[2], 0)  # Turn off blue LED

    response_json = analyze_image(pic_name)
    if response_json:
        print("")
        print(f"\033[35m[!] [Hazard Dectation Report] \033[0m")
        print(f"\033[37m[!] {response_json.get('answer', 'Unknown')}: {response_json.get('reason', 'No reason provided')}\033[0m")
        print("")

    json_file = 'response.json'
    with open(json_file, 'w') as fid:
        fid.write(json.dumps(response_json, indent=4))

    ftp_upload(pic_name)
    ftp_upload(json_file)

    print(f"\033[33m[+] Upload complete. Uploaded files: {pic_name}, {json_file}\033[0m")


def ftp_upload(filename=None):
    if filename is None or not os.path.exists(filename):
        print("\033[31m[!] No such file exists.\033[0m")
        return

    print(f"\033[33m[+] FTP upload: {filename}\033[0m")
    try:
        # Start a thread to make the LED blink
        threading.Thread(target=rapid_blink, args=(pwm_led[1],)).start()
        ftp = FTP(host=ftp_addr)
        ftp.set_pasv(False)
        ftp.login(user=ftp_username, passwd=ftp_passwd)
        ftp.storbinary('STOR ' + f"capture/{filename}", open(filename, 'rb'))
        ftp.quit()
        print("\033[33m[+] FTP completed\033[0m")
    except Exception as e:
        print("\033[31m[!] FTP upload failed:", e, "\033[0m")
    finally:
        toggle_led(pwm_led[1], 0)  # Ensure green LED is off


def main():
    print("")
    print("\033[36mZenith Go Firmware", FIRMWARE_VERSION, "\033[0m")
    print("\033[36m© 2024 Zenith - All Rights Reserved\033[0m")
    print("")
    print("\033[33mCountdown starting...\033[0m")

    for i in range(5, 0, -1):
        print(f"\033[33mCountdown: {i}\033[0m")
        time.sleep(1)

    print("")
    print("\033[32m[!] Ready for button input\033[0m")
    print("")
    toggle_led(pwm_led[1], 25)  # Turn on green LED
    time.sleep(1)  # Set the delay to 1 second
    toggle_led(pwm_led[1], 0)  # Turn off green LED

    try:
        while True: 
            if GPIO.input(CAMERA_BTN) == GPIO.HIGH:
                if not btn_press:
                    grab_and_upload()
                    btn_press = True
                    toggle_led(pwm_led[0], 0)  # Turn off red LED
                    toggle_led(pwm_led[1], 25)  # Turn on green LED
                    print("")
                    print("\033[32m[!] Ready for button input\033[0m")
                    print("\033[33m[!] To end the program use Control+C\033[0m")
                    print("")
                    time.sleep(1)  # Set the delay to 1 second
                    toggle_led(pwm_led[1], 0)  # Turn off green LED
            else:
                btn_press = False

            time.sleep(0.2)
    except KeyboardInterrupt:
        toggle_led(pwm_led[2], 0)  # Turn off blue LED
        camera.close()
        GPIO.cleanup()
    except Exception as e:
        print("\033[31m[!] Error occurred:", e, "\033[0m")
        toggle_led(pwm_led[0], 25)  # Turn on red LED
        time.sleep(1)  # Set the delay to 1 second
        toggle_led(pwm_led[0], 0)  # Turn off red LED
        time.sleep(1)  # Set the delay to 1 second
    finally:
        print("")
        print("")
        print("\033[35m[!] Stay safe out there\033[0m")
        print("\033[35m[!] Goodbye and we love you! <3\033[0m")
        print("")


if __name__ == "__main__":
    main()
