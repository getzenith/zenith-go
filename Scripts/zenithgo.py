#!/usr/bin/python

# Zenith Go Firmware 20240224.05
# © 2024 Zenith - All Rights Reserved

# Import configuration
from config import FTP_USERNAME, FTP_PASSWORD, FTP_ADDRESS, OPENAI_API_KEY

import RPi.GPIO as GPIO
import uuid
from ftplib import FTP
from picamera import PiCamera
import time
import os
import base64
import requests
import json
import re

CAMERA_BTN = 22  # gpio 6

# LED pins (single LED w. multiple leads)
RED_LED = 11
GREEN_LED = 13
BLUE_LED = 15

# FTP info
ftp_username = FTP_USERNAME
ftp_passwd = FTP_PASSWORD
ftp_addr = FTP_ADDRESS

# Camera settings
camera = PiCamera()
camera.resolution = (1280, 720)

btn_press = False  # Keep track of the button state

# https://raspberrypihq.com/use-a-push-button-with-raspberry-pi-gpio/
GPIO.setwarnings(False)  # Ignore warning
GPIO.setmode(GPIO.BOARD)  # Use BCM GPIO numbering
GPIO.setup(CAMERA_BTN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)  # Setup INput buttons

pwm_led = []
# https://www.instructables.com/Raspberry-Pi-Tutorial-How-to-Use-a-RGB-LED/
for led in [RED_LED, GREEN_LED, BLUE_LED]:
    GPIO.setup(led, GPIO.OUT)  # Setup OUTput LED
    pwm_led.append(GPIO.PWM(led, 100))
    pwm_led[-1].start(0)


def toggle_led(duty_cycle=0):
    # Change the duty cycle of all pins
    for p in pwm_led:
        p.ChangeDutyCycle(duty_cycle)


# Function to encode the image to base64
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


# Function to extract JSON string from response
def extract_json_text(text):
    pattern = r"\{.*\}"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        json_text = match.group()
        json_obj = json.loads(json_text)
        return json_obj
    else:
        return None


# Function to analyze the image for a potential hazard
def analyze_image(image_path):
    print("[+] Sending image to OpenAI for analysis...")

    # Set your OpenAI API key here
    api_key = OPENAI_API_KEY

    # Encode the image
    base64_image = encode_image(image_path)

    # Define your question
    question = "What potential hazards can you identify in this image?"

    # Prepare the headers and payload for the request
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
        # Send the request
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
        response_json = response.json()

        print("[+] Received response from OpenAI:")
        print(response_json)  # Print the response for debugging purposes

        # Extract the embedded JSON response
        # return extract_json_text(response_json['choices'][0]['message']['content'])

    except Exception as e:
        print("OpenAI API call failed:", e)
        return None



def grab_and_upload():
    print("[+] Getting photo.")

    # Turn on the light (white)
    toggle_led(100)

    # Set picture name
    pic_name = f"img_{str(time.time())}.jpg"

    # Capture the image to disk
    camera.capture(pic_name)

    # Turn off the light
    toggle_led()

    # Analyze the image and save the JSON response
    response_json = analyze_image(pic_name)
    json_file = 'response.json'
    with open(json_file, 'w') as fid:
        fid.write(json.dumps(response_json, indent=4))

    # Upload the picture and OpenAI response
    ftp_upload(pic_name)
    ftp_upload(pic_name, latest=True)  # Upload as latest_image.jpg

    print(f"[+] Upload complete. Uploaded file: {pic_name}")
    if response_json:
        print(f"[Hazard Detected] {response_json['answer']}: {response_json['reason']}")


def ftp_upload(remote_filename, local_filename=None, latest=False):
    if local_filename is None or not os.path.exists(local_filename):
        return

    print("[+] FTP upload")

    with FTP(host=ftp_addr) as ftp:
        try:
            ftp.login(user=ftp_username, passwd=ftp_passwd)
            
            # If uploading as latest, delete the existing file first
            if latest:
                try:
                    ftp.delete("capture/latest_image.jpg")
                except Exception as e:
                    print("Could not delete existing latest_image.jpg:", e)

            # Upload the file
            with open(local_filename, 'rb') as file:
                ftp.storbinary(f'STOR capture/{remote_filename}', file)

            print("[+] FTP completed")

        except Exception as e:
            print("FTP upload failed:", e)


def main():
    print("Zenith Go Firmware 20240224.05")
    print("© 2024 Zenith - All Rights Reserved")
    print("")
    print("Countdown starting...")

    for i in range(5, 0, -1):
        print(f"Countdown: {i}")
        time.sleep(1)



    try:
        while True:
            # Check if the camera button was pressed
            print("Ready for button input")
            if GPIO.input(CAMERA_BTN) == GPIO.HIGH:
                # It is, verify this is the first time (rising edge)
                if btn_press is False:
                    grab_and_upload()
                    btn_press = True  # Reset when let go
            else:
                # Button is not being pressed
                btn_press = False

            # Sleep for 0.2 seconds
            time.sleep(0.2)  # zZz...

    except KeyboardInterrupt:
        # Turn off the light
        toggle_led()
        # p.stop()

        camera.close()
        GPIO.cleanup()  # clean up GPIO on CTRL+C exit

    print("[+] Done")


if __name__ == "__main__":
    main()
