import base64
import os.path
import time
import logging

from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_otp(after_ts, retry=False):
  """Shows basic usage of the Gmail API.
  Lists the user's Gmail labels.
  """
  creds = None
  # The file token.json stores the user's access and refresh tokens, and is
  # created automatically when the authorization flow completes for the first
  # time.
  if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
  # If there are no (valid) credentials available, let the user log in.
  if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
      creds.refresh(Request())
    else:
      flow = InstalledAppFlow.from_client_secrets_file(
          "credentials.json", SCOPES
      )
      creds = flow.run_local_server(port=58484)
    # Save the credentials for the next run
    with open("token.json", "w") as token:
      token.write(creds.to_json())

  try:
    # Call the Gmail API
    service = build("gmail", "v1", credentials=creds)
    results = service.users().messages().list(
        userId="me", maxResults=1,
        q="from: ticketadmin@irctc.co.in 'One Time Password (OTP)' newer_than:1h").execute()
    msgs = results.get("messages", [])
    if not msgs:
        logging.info('OTP not received.')

    for m in msgs:
        msg = service.users().messages().get(userId="me", id=m['id']).execute()
        rcv_time = datetime.utcfromtimestamp(int(msg['internalDate']) // 1000)
        if rcv_time < after_ts:
            logging.info(f'Ignoring stale OTP email at {rcv_time}')
            continue
        body = base64.urlsafe_b64decode(msg.get('payload', {}).get('body', {}).get('data', '').encode('ASCII')).decode('utf-8')
        otp = body.split('<B>')[1].split('</B>')[0].strip()
        return otp

    time.sleep(1)
    return get_otp(after_ts, retry)

  except:
    logging.exception('Error retrieving OTP')
    if retry:
        time.sleep(1)
        return get_otp(after_ts, retry)

