import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_smtp_connection():
    server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
    server.starttls()
    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
    return server


def send_account_credentials(doctor_email: str, doctor_name: str, hospital_name: str, loginid: str, temp_password: str) -> bool:
    """신규 계정 문의 처리 후 의사 이메일로 아이디/임시 비밀번호 발송."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("[Email] SMTP 설정 없음 — 이메일 발송 건너뜀")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = settings.SMTP_FROM
        msg["To"] = doctor_email
        msg["Subject"] = f"[MediPaw] {hospital_name} 계정 발급 안내"

        html = f"""
        <html><body style="font-family: sans-serif; color: #222; max-width: 480px; margin: 0 auto;">
          <h2 style="color: #2f6f67;">MediPaw 계정 발급 안내</h2>
          <p>안녕하세요, <strong>{doctor_name}</strong> 원장님.</p>
          <p>아래 정보로 MediPaw 시스템에 로그인하실 수 있습니다.</p>
          <table style="border-collapse: collapse; width: 100%; margin: 20px 0;">
            <tr style="background: #f5f9f8;">
              <th style="padding: 12px; border: 1px solid #ddd; text-align: left; width: 40%;">아이디</th>
              <td style="padding: 12px; border: 1px solid #ddd;"><strong>{loginid}</strong></td>
            </tr>
            <tr>
              <th style="padding: 12px; border: 1px solid #ddd; text-align: left;">임시 비밀번호</th>
              <td style="padding: 12px; border: 1px solid #ddd;"><strong>{temp_password}</strong></td>
            </tr>
          </table>
          <p style="color: #e53935;">⚠️ 보안을 위해 로그인 후 반드시 비밀번호를 변경해주세요.</p>
          <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
          <p style="font-size: 12px; color: #999;">본 메일은 발신 전용입니다. 문의사항은 MediPaw 고객지원팀으로 연락해주세요.</p>
        </body></html>
        """
        msg.attach(MIMEText(html, "html"))

        with _build_smtp_connection() as server:
            server.sendmail(settings.SMTP_FROM, doctor_email, msg.as_string())

        logger.info(f"[Email] 계정 발급 메일 발송 완료 → {doctor_email}")
        return True

    except Exception as e:
        logger.error(f"[Email] 발송 실패: {e}")
        return False


def send_contact_reply(to_email: str, to_name: str, original_message: str, reply_message: str) -> bool:
    """홈페이지 문의 답장 이메일 발송."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("[Email] SMTP 설정 없음 — 이메일 발송 건너뜀")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = settings.SMTP_FROM
        msg["To"] = to_email
        msg["Subject"] = "[MediPaw] 문의 답변 안내"

        original_html = original_message.replace("\n", "<br>")
        reply_html = reply_message.replace("\n", "<br>")

        html = f"""
        <html><body style="font-family: sans-serif; color: #222; max-width: 520px; margin: 0 auto;">
          <h2 style="color: #2f6f67;">MediPaw 문의 답변</h2>
          <p>안녕하세요, <strong>{to_name}</strong>님. 문의해 주셔서 감사합니다.</p>

          <p style="margin-top: 24px; font-size: 13px; font-weight: bold; color: #555;">📩 보내주신 문의</p>
          <div style="background: #f8f8f8; border-left: 3px solid #ccc; padding: 14px 18px; margin: 8px 0 20px; font-size: 14px; line-height: 1.7; color: #444;">
            {original_html}
          </div>

          <p style="font-size: 13px; font-weight: bold; color: #555;">💬 MediPaw 답변</p>
          <div style="background: #f0f7f6; border-left: 3px solid #2f6f67; padding: 14px 18px; margin: 8px 0; font-size: 14px; line-height: 1.7; color: #222;">
            {reply_html}
          </div>

          <hr style="border: none; border-top: 1px solid #eee; margin: 28px 0;">
          <p style="font-size: 12px; color: #999;">추가 문의사항은 <a href="mailto:{settings.SMTP_FROM}" style="color: #2f6f67;">{settings.SMTP_FROM}</a>으로 연락해주세요.</p>
        </body></html>
        """
        msg.attach(MIMEText(html, "html"))

        with _build_smtp_connection() as server:
            server.sendmail(settings.SMTP_FROM, to_email, msg.as_string())

        logger.info(f"[Email] 문의 답장 발송 완료 → {to_email}")
        return True

    except Exception as e:
        logger.error(f"[Email] 문의 답장 발송 실패: {e}")
        return False


def send_account_inquiry_to_cs(doctor_name: str, hospital_name: str, business_number: str, license_number: str, doctor_email: str) -> bool:
    """계정 조회 실패 시 CS팀에 알림 이메일 발송 (Reply-To: 의사 이메일)."""
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD or not settings.CS_EMAIL:
        logger.warning("[Email] SMTP/CS 설정 없음 — 이메일 발송 건너뜀")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = settings.SMTP_FROM
        msg["To"] = settings.CS_EMAIL
        msg["Reply-To"] = doctor_email
        msg["Subject"] = f"[계정 문의] {hospital_name} - {doctor_name} 원장"

        html = f"""
        <html><body style="font-family: sans-serif; color: #222; max-width: 480px; margin: 0 auto;">
          <h2 style="color: #2f6f67;">[MediPaw] 계정 문의 접수</h2>
          <table style="border-collapse: collapse; width: 100%; margin: 20px 0;">
            <tr style="background: #f5f9f8;">
              <th style="padding: 12px; border: 1px solid #ddd; text-align: left; width: 40%;">병원명</th>
              <td style="padding: 12px; border: 1px solid #ddd;">{hospital_name}</td>
            </tr>
            <tr>
              <th style="padding: 12px; border: 1px solid #ddd; text-align: left;">의사명</th>
              <td style="padding: 12px; border: 1px solid #ddd;">{doctor_name}</td>
            </tr>
            <tr style="background: #f5f9f8;">
              <th style="padding: 12px; border: 1px solid #ddd; text-align: left;">사업자등록번호</th>
              <td style="padding: 12px; border: 1px solid #ddd;">{business_number}</td>
            </tr>
            <tr>
              <th style="padding: 12px; border: 1px solid #ddd; text-align: left;">면허번호</th>
              <td style="padding: 12px; border: 1px solid #ddd;">{license_number}</td>
            </tr>
            <tr style="background: #f5f9f8;">
              <th style="padding: 12px; border: 1px solid #ddd; text-align: left;">이메일</th>
              <td style="padding: 12px; border: 1px solid #ddd;">{doctor_email}</td>
            </tr>
          </table>
          <p>위 정보를 확인 후 계정을 생성해주세요.</p>
        </body></html>
        """
        msg.attach(MIMEText(html, "html"))

        with _build_smtp_connection() as server:
            server.sendmail(settings.SMTP_FROM, settings.CS_EMAIL, msg.as_string())

        logger.info(f"[Email] CS 알림 메일 발송 완료 → {settings.CS_EMAIL}")
        return True

    except Exception as e:
        logger.error(f"[Email] CS 알림 발송 실패: {e}")
        return False
