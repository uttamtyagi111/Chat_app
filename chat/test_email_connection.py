import smtplib
import os
from dotenv import load_dotenv

load_dotenv()

email_user = os.getenv('EMAIL_HOST_USER')
email_password = os.getenv('EMAIL_HOST_PASSWORD')
email_host = os.getenv('EMAIL_HOST')
email_port = int(os.getenv('EMAIL_PORT', 587))

# Debug output
print(f"EMAIL_HOST: '{email_host}'")
print(f"EMAIL_PORT: {email_port}")
print(f"EMAIL_HOST_USER: '{email_user}'")
print(f"EMAIL_HOST_PASSWORD: {'*' * len(email_password) if email_password else 'None'}")
print()

try:
    print(f"Connecting to {email_host}:{email_port}...")
    
    with smtplib.SMTP(email_host, email_port) as server:
        print("✅ SMTP connection established")
        
        server.starttls()
        print("✅ TLS encryption started")
        
        server.login(email_user, email_password)
        print("✅ Login successful")

        from_address = email_user
        to_address = 'uttam@wishgeekstechserve.com'  
        subject = 'Test Email'
        body = 'This is a test email to check SMTP connection.'

        # Proper email formatting
        message = f"""From: {from_address}
To: {to_address}
Subject: {subject}

{body}"""

        server.sendmail(from_address, to_address, message)
        print('✅ Email sent successfully!')

except smtplib.SMTPAuthenticationError as e:
    print(f"❌ Authentication failed: {e}")
    print("Check your username and password")
    
except smtplib.SMTPConnectError as e:
    print(f"❌ Connection failed: {e}")
    print("Check your SMTP host and port")
    
except smtplib.SMTPException as e:
    print(f"❌ SMTP error: {e}")
    
except Exception as e:
    print(f"❌ Failed to send email: {e}")
    print(f"Error type: {type(e).__name__}")

