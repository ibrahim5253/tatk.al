import base64
import io
import requests
import time

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from PIL import Image

null = None
true = True
false = False

## Config

BASE_URL = 'https://www.irctc.co.in/eticketing/protected/mapps1'

ENDPOINTS = {
    "login_captcha": {"path": "loginCaptcha", "method": "get"},
    "user": {"path": "validateUser?source=3", "method": "get"},

    "avl_fare_n":
    {"path": "avlFarenquiry/{train}/{date}/{src}/{dst}/{cls}/{qt}/N",
     "payload": lambda *,train,date,src,dst,cls,qt,**kwargs:
     {
         "paymentFlag": "N",
         "concessionBooking": false,
         "ftBooking": false,
         "loyaltyRedemptionBooking": false,
         "ticketType": "E",
         "quotaCode": qt,
         "moreThanOneDay": true,
         "trainNumber": train,
         "fromStnCode": src,
         "toStnCode": dst,
         "isLogedinReq": true,
         "journeyDate": date,
         "classCode": cls 
     }},

    "boarding_station":
    {"path": "boardingStationEnq",
     "payload": lambda *,train,date,src,dst,cls,qt,**kwargs:
     {
         "clusterFlag": "N",
         "onwardFlag": "N",
         "cod": "false",
         "reservationMode": "WS_TA_B2C",
         "autoUpgradationSelected": false,
         "gnToCkOpted": false,
         "paymentType": 1,
         "twoPhaseAuthRequired": false,
         "captureAddress": 0,
         "alternateAvlInputDTO": [
             {
                 "trainNo": train,
                 "destStn": dst,
                 "srcStn": src,
                 "jrnyDate": date,
                 "quotaCode": qt,
                 "jrnyClass": cls,
                 "concessionPassengers": false
             }
         ],
         "passBooking": false,
         "journalistBooking": false
     }},

     "avl_fare_y":
     {"path": "allLapAvlFareEnq/Y",
      "payload": lambda *,user,train,date,src,dst,cls,qt,psgs,txnId,fc=None,**kwargs:
      {
          "clusterFlag": "N",
          "onwardFlag": "N",
          "cod": "false",
          "reservationMode": "WS_TA_B2C",
          "autoUpgradationSelected": false,
          "gnToCkOpted": false,
          "paymentType": "3",
          "twoPhaseAuthRequired": false,
          "captureAddress": 0,
          "wsUserLogin": user.json().get("userName"),
          "moreThanOneDay": false,
          "clientTransactionId": txnId,
          "boardingStation": src,
          "reservationUptoStation": dst,
          "ticketType": "E",
          "mainJourneyTxnId": null,
          "mainJourneyPnr": "",
          "captcha": "",
          "generalistChildConfirm": false,
          "ftBooking": false,
          "loyaltyRedemptionBooking": false,
          "nosbBooking": false,
          "warrentType": 0,
          "ftTnCAgree": false,
          "bookingChoice": 1,
          "bookingConfirmChoice": 1,
          "bookOnlyIfCnf": false,
          "returnJourney": null,
          "connectingJourney": false,
          "lapAvlRequestDTO": [
              {
                  "trainNo": train,
                  "journeyDate": date,
                  "fromStation": src,
                  "toStation": dst,
                  "journeyClass": cls,
                  "quota": qt,
                  "coachId": null,
                  "reservationChoice": "99",
                  "ignoreChoiceIfWl": true,
                  "travelInsuranceOpted": "false",
                  "warrentType": 0,
                  "coachPreferred": false,
                  "autoUpgradation": false,
                  "bookOnlyIfCnf": false,
                  "addMealInput": null,
                  "concessionBooking": false,
                  "passengerList": [
                      {
                          "passengerName": p['name'],
                          "passengerAge": p['age'],
                          "passengerGender": p['gender'],
                          "passengerBerthChoice": p['pref'],
                          "passengerFoodChoice": "D" if fc else null,
                          "passengerBedrollChoice": null,
                          "passengerNationality": "IN",
                          "passengerCardTypeMaster": null,
                          "passengerCardNumberMaster": null,
                          "psgnConcType": null,
                          "psgnConcCardId": null,
                          "psgnConcDOB": null,
                          "psgnConcCardExpiryDate": null,
                          "psgnConcDOBP": null,
                          "softMemberId": null,
                          "softMemberFlag": null,
                          "psgnConcCardExpiryDateP": null,
                          "passengerVerified": false,
                          "masterPsgnId": null,
                          "mpMemberFlag": null,
                          "passengerForceNumber": null,
                          "passConcessionType": "0",
                          "passUPN": null,
                          "passBookingCode": null,
                          "passengerSerialNumber": i,
                          "childBerthFlag": true,
                          "passengerCardType": "NULL_IDCARD",
                          "passengerIcardFlag": false,
                          "passengerCardNumber": null
                          } for i, p in enumerate(psgs)
                      ],
                  "ssQuotaSplitCoach": "N"
                }],
                "gstDetails": {
                        "gstIn": "",
                        "error": null
                        },
                "mobileNumber": user.json()["mobile"]
        }},

    "captcha_verify": {"path": "captchaverify/{txnId}/BOOKINGWS/{captcha}",
                       "method": "get"},

    "payment_init":
    {"path": "bookingInitPayment/{txnId}?insurenceApplicable=",
     "payload": lambda *,amt,txnPass=None,**kwargs:
     {
         "bankId": 1000,
         "txnType": 7,
         "paramList": [
             {
                 "key": "TXN_PASSWORD",
                 "value": txnPass if txnPass else ""
                 }
             ],
         "amount": amt,
         "transationId": 0,
         "txnStatus": 1
         }},

     "payment_verify":
     {"path": "verifyPayment/{txnId}",
      "payload": lambda *,txnId=None,**kwargs: kwargs}
}

## Utilities

def now():
    return str(int(time.time() * 1000))

def tobase36(n):
    alpha = '0123456789abcdefghijklmnopqrstuvwxyz'
    chars = []
    n = int(n)
    while n>0:
        d = n%36
        chars.append(alpha[d])
        n = n // 36
    return ''.join(reversed(chars))

def user_input(prompt):
    return input(f'{prompt}\n>>> ') 

def solve_captcha(captcha):
    im = Image.open(io.BytesIO(base64.b64decode(captcha)))
    im.show()

    return user_input('Enter captcha')

def encrypt(e, t):
    key = e.encode('utf-8')
    plaintext = t.encode('utf-8')
    iv = key  # Use the parsed key as the initialization vector

    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pad(plaintext, AES.block_size))

    return base64.b64encode(ciphertext).decode('utf-8')

def api_call(endpoint, *, headers={}, **kwargs):
    endpoint = ENDPOINTS[endpoint]
    path = endpoint['path']
    method = endpoint.get('method', 'post')
    url = f"{BASE_URL}/{path}".format(**kwargs)

    if method == 'post':
        payload = endpoint['payload'](**kwargs)
        response = requests.post(url, headers=headers, json=payload)
    else:
        response = requests.get(url, headers=headers)

    return response

## Logged-in session

class Session(object):
    def __init__(self, loginid, pwd, *, txnPass=None):
        self._txnPass = txnPass
        captcha = api_call("login_captcha"
                           , method='get'
                           , headers={'Greq': now()}).json()
        self._uid = captcha['status']

        captcha_answer = solve_captcha(captcha['captchaQuestion'])

        creds = '#UP#'.join([loginid
                             , base64.b64encode(pwd.encode('utf-8')).decode('utf-8')
                             , now()])
        key = (captcha_answer + self._uid)[:16]
        token = {
            'grant_type': 'password',
            'captcha': captcha_answer,
            'uid': self._uid,
            'data': encrypt(key, creds),
            'otpLogin': False,
            'lso': '',
            'encodedPwd': True
        }

        self._access_token = \
            requests.post('https://www.irctc.co.in/authprovider/webtoken', data=token).json()
        self._csrf_token = now()
        self.user = self._api_call("user")

    def _api_call(self, endpoint, **kwargs):
        response = api_call(
            endpoint,
            headers={'Greq': self._uid,
                     'Authorization': f'Bearer {self._access_token["access_token"]}',
                     'Spa-Csrf-Token': self._csrf_token},
            **kwargs
        )
        self._csrf_token = response.headers['csrf-token']
        return response

    def init_journey(self, journey):
        self.journey = journey
        self._avl_fare_n = \
            self._api_call("avl_fare_n", **journey)

    def enquire_boarding_stations(self):
        self._boarding_station = \
            self._api_call("boarding_station", **self.journey)
        self._fc = self._boarding_station.json()['bkgCfgs'][0]['foodChoiceEnabled'] == 'true'

    def add_passengers(self, *psgs):
        self._txn_id = tobase36(now())
        self._avl_fare_y = \
            self._api_call("avl_fare_y", **(self.journey | {'psgs': psgs,
                                                            'txnId': self._txn_id,
                                                            'user': self.user,
                                                            'fc': self._fc}))
        self._review_captcha = self._avl_fare_y.json()['captchaDto']['captchaQuestion']

    def confirm_booking(self):
        captcha = solve_captcha(self._review_captcha)
        self._review_status = self._api_call("captcha_verify", txnId=self._txn_id, captcha=captcha)

    def pay(self):
        self._payment_init = self._api_call("payment_init"
                                            , txnId=self._txn_id
                                            , amt=self._avl_fare_y.json()['totalCollectibleAmount']
                                            , txnPass=self._txnPass)
        otp = user_input('Enter OTP:')
        self._payment_verify = \
            self._api_call("payment_verify",
                           **(self._payment_init.json()
                              | {'paramList':[{'key': 'OTP', 'value': otp}, 
                                              {'key': 'TXN_TYPE', 'value': 'undefined'}],
                                 'txnId': self._txn_id}))
