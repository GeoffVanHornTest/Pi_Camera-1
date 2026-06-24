# notifier.py


import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import config


_last_sent = 0
#This is a module-level variable that stores the timestamp 
#of the last alert sent

def send_alert(snapshot_path):
    global _last_sent
    # tells Python we want to modify the module-level variable, 
    # not create a new local on
    now = time.time()
    # returns the current time in seconds

    if now - _last_sent < config.NOTIFICATION_COOLDOWN_SEC:
        # is how many seconds have passed since the last alert
        #If that gap is less than our cooldown (60 seconds), we return immediately — 
        # no email sent, nothing logged, just quietly exits the function
        
        return
    
    msg = MIMEMultipart()
    msg["From"]    = config.GMAIL_SENDER
    msg["To"]      = config.GMAIL_RECIPIENT
    msg["Subject"] = "Motion Detected!"

    body = "Motion was detected. See the attached snapshot."
    msg.attach(MIMEText(body, "plain"))
    #adds that text part to the email container we built in the last step

    with open(snapshot_path, "rb") as f:
        # opens the image file in read binary mode
        attachment = MIMEBase("application", "octet-stream")
        # creates a generic binary attachment container
        attachment.set_payload(f.read())
        # loads the raw image bytes into that container

    encoders.encode_base64(attachment)
    attachment.add_header("Content-Disposition", f"attachment; filename={snapshot_path}")
     # tells the email client this is a downloadable attachment and sets the filename
    msg.attach(attachment)
    # adds it to the email alongside the text body

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        # opens a connection to Gmail's mail server on port 587
        server.ehlo()
        # introduces our client to the server — a required SMTP handshake
        server.starttls()
        # upgrades the connection to encrypted TLS — never send credentials without this
        server.login(config.GMAIL_SENDER, config.GMAIL_PASSWORD)
        # authenticates with your Gmail address and App Password
        server.sendmail(config.GMAIL_SENDER, config.GMAIL_RECIPIENT, msg.as_string())
        # sends the fully assembled email

    _last_sent = time.time()
    # records the current time so the cooldown starts counting — this line is outside the 
    # with block but still inside send_alert()
