# utils/email_sender.py
import logging
import os
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.conf import settings
from smtplib import SMTPException
import socket
from email.utils import formataddr
from django.core.mail import get_connection
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

def send_otp_email(email, otp, purpose="password_reset"):
    """
    Send an OTP email to the specified address with HTML content.
    
    Args:
        email (str): Recipient email address
        otp (str): OTP code to send
        purpose (str): Purpose of OTP - 'password_reset', 'registration', etc.
    
    Returns:
        dict: {'success': bool, 'error': str or None}
    """
    try:
        # Validate inputs
        if not email or not otp:
            return {'success': False, 'error': 'Email and OTP are required'}
        
        # Get email settings from environment
        email_host = os.getenv('EMAIL_HOST')
        email_port = int(os.getenv('EMAIL_PORT', 587))
        email_user = os.getenv('EMAIL_HOST_USER')
        email_password = os.getenv('EMAIL_HOST_PASSWORD')
        email_use_tls = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
        
        # Debug email settings
        logger.info(f"Email settings - HOST: '{email_host}', PORT: {email_port}, USER: '{email_user}'")
        
        # Test connection first with direct settings
        try:
            import smtplib
            with smtplib.SMTP(email_host, email_port) as server:
                if email_use_tls:
                    server.starttls()
                server.login(email_user, email_password)
            logger.info("Email connection test successful")
        except Exception as conn_error:
            logger.error(f"Email connection test failed: {str(conn_error)}")
            return {'success': False, 'error': f'Email service connection failed: {str(conn_error)}'}
        
        # Determine subject and template based on purpose
        if purpose == "password_reset":
            subject = 'Password Reset OTP - Wish Geeks Techserve'
            template = 'authentication/password_reset_otp.html'
        elif purpose == "registration":
            subject = 'Registration OTP - Wish Geeks Techserve'
            template = 'authentication/registration_otp.html'
        else:
            subject = 'Your OTP - Wish Geeks Techserve'
            template = 'authentication/generic_otp.html'
        
        # Prepare email context
        context = {
            'otp': otp,
            'email': email,
            'company_name': 'Wish Geeks Techserve',
            'support_email': os.getenv('SUPPORT_EMAIL', 'support@wishgeekstechserve.com')
        }
        
        # Render HTML content
        try:
            html_content = render_to_string(template, context)
        except Exception as template_error:
            logger.error(f"Template rendering failed: {str(template_error)}")
            # Fallback to simple HTML
            html_content = f"""
            <html>
            <body>
                <h2>Your OTP Code</h2>
                <p>Dear User,</p>
                <p>Your OTP code is: <strong>{otp}</strong></p>
                <p>This code will expire in 10 minutes.</p>
                <p>Best regards,<br>Wish Geeks Techserve</p>
            </body>
            </html>
            """
        
        # Create email message
        from_email = os.getenv('DEFAULT_FROM_EMAIL', email_user)
        from_name = os.getenv('EMAIL_FROM_NAME', 'Wish Geeks Techserve')
        reply_to_email = os.getenv('REPLY_TO_EMAIL', email_user)
        
        # Create custom email message using smtplib directly
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = formataddr((from_name, from_email))
        msg['To'] = email
        msg['Reply-To'] = reply_to_email
        
        # Create HTML part
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        # Send email using direct SMTP
        with smtplib.SMTP(email_host, email_port) as server:
            if email_use_tls:
                server.starttls()
            server.login(email_user, email_password)
            server.send_message(msg)
        
        logger.info(f"OTP email sent successfully to {email} for {purpose}")
        return {'success': True, 'error': None}
        
    except SMTPException as e:
        error_msg = f"SMTP error while sending OTP to {email}: {str(e)}"
        logger.error(error_msg)
        return {'success': False, 'error': 'Email service temporarily unavailable. Please try again later.'}
        
    except socket.gaierror as e:
        error_msg = f"DNS/Network error while sending OTP to {email}: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Check EMAIL_HOST setting: '{os.getenv('EMAIL_HOST', 'NOT_SET')}'")
        return {'success': False, 'error': 'Email server connection failed. Please contact support.'}
        
    except ConnectionRefusedError as e:
        error_msg = f"Connection refused while sending OTP to {email}: {str(e)}"
        logger.error(error_msg)
        return {'success': False, 'error': 'Email server unavailable. Please try again later.'}
        
    except Exception as e:
        error_msg = f"Unexpected error while sending OTP to {email}: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Email settings - HOST: '{os.getenv('EMAIL_HOST', 'NOT_SET')}', PORT: {os.getenv('EMAIL_PORT', 'NOT_SET')}")
        return {'success': False, 'error': 'Failed to send email. Please contact support.'}


def send_password_reset_confirmation(email, username=None):
    """
    Send confirmation email after successful password reset.
    
    Args:
        email (str): Recipient email address
        username (str): Username (optional)
    
    Returns:
        dict: {'success': bool, 'error': str or None}
    """
    try:
        subject = 'Password Reset Successful - Wish Geeks Techserve'
        
        context = {
            'username': username or email.split('@')[0],
            'email': email,
            'company_name': 'Wish Geeks Techserve',
            'support_email': os.getenv('SUPPORT_EMAIL', 'support@wishgeekstechserve.com')
        }
        
        try:
            html_content = render_to_string('authentication/password_reset_success.html', context)
        except Exception:
            # Fallback HTML
            html_content = f"""
            <html>
            <body>
                <h2>Password Reset Successful</h2>
                <p>Dear {context['username']},</p>
                <p>Your password has been successfully reset.</p>
                <p>If you did not request this change, please contact our support team immediately.</p>
                <p>Best regards,<br>Wish Geeks Techserve</p>
            </body>
            </html>
            """
        
        # Get email settings from environment
        email_host = os.getenv('EMAIL_HOST')
        email_port = int(os.getenv('EMAIL_PORT', 587))
        email_user = os.getenv('EMAIL_HOST_USER')
        email_password = os.getenv('EMAIL_HOST_PASSWORD')
        email_use_tls = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
        
        from_email = os.getenv('DEFAULT_FROM_EMAIL', email_user)
        from_name = os.getenv('EMAIL_FROM_NAME', 'Wish Geeks Techserve')
        
        # Create email using smtplib directly
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = formataddr((from_name, from_email))
        msg['To'] = email
        
        # Create HTML part
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        # Send email using direct SMTP
        with smtplib.SMTP(email_host, email_port) as server:
            if email_use_tls:
                server.starttls()
            server.login(email_user, email_password)
            server.send_message(msg)
        
        logger.info(f"Password reset confirmation sent to {email}")
        return {'success': True, 'error': None}
        
    except Exception as e:
        logger.error(f"Failed to send password reset confirmation to {email}: {str(e)}")
        return {'success': False, 'error': 'Failed to send confirmation email'}


def test_email_connection():
    """
    Test email connection and settings.
    
    Returns:
        dict: {'success': bool, 'error': str or None, 'details': dict}
    """
    try:
        # Get email settings from environment
        email_host = os.getenv('EMAIL_HOST')
        email_port = int(os.getenv('EMAIL_PORT', 587))
        email_user = os.getenv('EMAIL_HOST_USER')
        email_password = os.getenv('EMAIL_HOST_PASSWORD')
        email_use_tls = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
        
        details = {
            'host': email_host or 'NOT_SET',
            'port': email_port,
            'user': email_user or 'NOT_SET',
            'use_tls': email_use_tls,
            'default_from': os.getenv('DEFAULT_FROM_EMAIL', email_user) or 'NOT_SET',
        }
        
        logger.info(f"Testing email connection with settings: {details}")
        
        # Test connection using direct SMTP
        import smtplib
        with smtplib.SMTP(email_host, email_port) as server:
            if email_use_tls:
                server.starttls()
            server.login(email_user, email_password)
        
        return {
            'success': True, 
            'error': None, 
            'details': details,
            'message': 'Email connection successful'
        }
        
    except Exception as e:
        logger.error(f"Email connection test failed: {str(e)}")
        return {
            'success': False, 
            'error': str(e), 
            'details': details if 'details' in locals() else {},
            'message': 'Email connection failed'
        }