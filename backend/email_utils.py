"""
Email notification service for assessment completion.
Uses SMTP for sending emails (Gmail or other SMTP providers).
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

try:
    from backend.config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, NOTIFICATION_EMAIL
except ImportError:
    from config import SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, NOTIFICATION_EMAIL


async def send_email(
    recipient: str,
    subject: str,
    html_content: str,
) -> bool:
    """
    Send email via SMTP.
    Returns True if successful, False if email not configured or error occurred.
    """
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        print("[Email] Email not configured. Skipping notification.")
        return False
    
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = recipient
        
        part = MIMEText(html_content, "html")
        msg.attach(part)
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [recipient], msg.as_string())
        
        print(f"[Email] Sent to {recipient}")
        return True
    except Exception as e:
        print(f"[Email Error] Failed to send to {recipient}: {e}")
        return False


def assessment_complete_email(
    candidate_name: str,
    overall_score: float,
    recommendation: str,
    report_url: str,
) -> str:
    """Generate HTML email for assessment completion."""
    score_color = "#2b7a50" if overall_score >= 7 else "#b87333" if overall_score >= 5 else "#c0392b"
    rec_color = "#2b7a50" if recommendation == "Move to next round" else "#b87333" if recommendation == "Consider with reservations" else "#c0392b"
    
    html = f"""
    <html>
      <head>
        <style>
          body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #333; }}
          .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
          .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 20px; text-align: center; border-radius: 8px 8px 0 0; }}
          .content {{ background: #f9f9f9; padding: 30px 20px; border-radius: 0 0 8px 8px; }}
          .score-box {{ background: white; padding: 20px; border-radius: 6px; margin: 20px 0; text-align: center; border-left: 4px solid {score_color}; }}
          .score-number {{ font-size: 48px; font-weight: bold; color: {score_color}; }}
          .rec-box {{ background: {rec_color}15; padding: 15px; border-radius: 6px; margin: 20px 0; border-left: 4px solid {rec_color}; }}
          .rec-text {{ color: {rec_color}; font-weight: 600; }}
          .button {{ display: inline-block; padding: 12px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 6px; margin: 20px 0; }}
          .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 20px; }}
        </style>
      </head>
      <body>
        <div class="container">
          <div class="header">
            <h1>Assessment Complete</h1>
            <p>{candidate_name}'s screening interview has been completed and assessed.</p>
          </div>
          <div class="content">
            <div class="score-box">
              <div>Overall Score</div>
              <div class="score-number">{overall_score:.1f}/10</div>
            </div>
            
            <div class="rec-box">
              <div class="rec-text">📋 {recommendation}</div>
            </div>
            
            <p>Review the full assessment report and screening details:</p>
            <center>
              <a href="{report_url}" class="button">View Full Report →</a>
            </center>
            
            <p style="color: #666; font-size: 14px;">
              Use the dashboard to filter results, export data, and manage bulk interviews with your team.
            </p>
          </div>
          <div class="footer">
            <p>Audisift</p>
          </div>
        </div>
      </body>
    </html>
    """
    return html


def bulk_links_email(
    recipient_email: str,
    interview_links: list[str],
    batch_label: str = "Interview Batch",
) -> str:
    """Generate HTML email for bulk interview links."""
    links_html = ""
    for i, link in enumerate(interview_links, 1):
        links_html += f"""
        <tr>
          <td style="padding: 10px; border-bottom: 1px solid #eee;">
            Link {i}
          </td>
          <td style="padding: 10px; border-bottom: 1px solid #eee;">
            <code style="background: #f5f5f5; padding: 8px 12px; border-radius: 4px; font-family: monospace; font-size: 12px;">
              {link}
            </code>
          </td>
        </tr>
        """
    
    html = f"""
    <html>
      <head>
        <style>
          body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #333; }}
          .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
          .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 20px; text-align: center; border-radius: 8px 8px 0 0; }}
          .content {{ background: #f9f9f9; padding: 30px 20px; border-radius: 0 0 8px 8px; }}
          table {{ width: 100%; border-collapse: collapse; background: white; margin: 20px 0; }}
          .button {{ display: inline-block; padding: 12px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 6px; margin: 20px 0; }}
          .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 20px; }}
        </style>
      </head>
      <body>
        <div class="container">
          <div class="header">
            <h1>Interview Links Generated</h1>
            <p>{batch_label} — {len(interview_links)} links ready to share</p>
          </div>
          <div class="content">
            <p>Your bulk interview links have been generated. Share these with candidates to start screening:</p>
            
            <table>
              <thead>
                <tr style="background: #f5f5f5;">
                  <th style="padding: 10px; text-align: left;">Link #</th>
                  <th style="padding: 10px; text-align: left;">URL (click to copy)</th>
                </tr>
              </thead>
              <tbody>
                {links_html}
              </tbody>
            </table>
            
            <p style="color: #666; font-size: 14px;">
              <strong>Tip:</strong> Each link is unique and can only be used once. Results appear in your dashboard after the candidate completes the interview.
            </p>
          </div>
          <div class="footer">
            <p>Audisift</p>
          </div>
        </div>
      </body>
    </html>
    """
    return html


def candidate_invite_email(
    candidate_name: str,
    email: str,
    password: str,
    login_url: str,
) -> str:
    """Generate HTML email for candidate invitation."""
    html = f"""
    <html>
      <head>
        <style>
          body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #333; }}
          .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
          .header {{ background: linear-gradient(135deg, #111 0%, #333 100%); color: white; padding: 40px 20px; text-align: center; border-radius: 8px 8px 0 0; }}
          .content {{ background: #f9f9f9; padding: 30px 20px; border-radius: 0 0 8px 8px; border: 1px solid #eee; }}
          .info-box {{ background: white; padding: 20px; border-radius: 6px; margin: 20px 0; border: 1px solid #ddd; }}
          .info-row {{ margin: 10px 0; font-size: 16px; }}
          .info-label {{ font-weight: bold; color: #666; display: inline-block; width: 100px; }}
          .info-value {{ font-family: monospace; font-size: 16px; background: #eee; padding: 2px 6px; border-radius: 4px; }}
          .button {{ display: inline-block; padding: 12px 30px; background: #e52b50; color: white !important; text-decoration: none; border-radius: 6px; margin: 20px 0; font-weight: bold; }}
          .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 20px; }}
        </style>
      </head>
      <body>
        <div class="container">
          <div class="header">
            <h1>AI Screening Interview Invitation</h1>
            <p>Hello {candidate_name}, you have been invited to take a screening interview.</p>
          </div>
          <div class="content">
            <p>You have been invited to participate in an automated voice screening interview using Sarah, our AI Interviewer.</p>
            <p>The interview takes approximately 10 minutes. Please ensure you are in a quiet room with a functioning microphone. For the best experience, use Google Chrome or Microsoft Edge.</p>
            
            <div class="info-box">
              <div class="info-row">
                <span class="info-label">Email:</span>
                <span class="info-value" style="background: none; padding: 0;">{email}</span>
              </div>
              <div class="info-row">
                <span class="info-label">Password:</span>
                <span class="info-value">{password}</span>
              </div>
            </div>
            
            <p>Click the button below to sign in and begin your interview:</p>
            <center>
              <a href="{login_url}" class="button">Login & Start Interview &rarr;</a>
            </center>
            
            <p style="color: #666; font-size: 14px; margin-top: 20px;">
              If you have any issues logging in, please contact the recruiter who shared this invitation.
            </p>
          </div>
          <div class="footer">
            <p>Audisift</p>
          </div>
        </div>
      </body>
    </html>
    """
    return html

