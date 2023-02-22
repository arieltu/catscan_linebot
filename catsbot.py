from __future__ import unicode_literals
from flask import Flask, request, abort, render_template
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

from PIL import Image, ImageOps
# from tensorflow.keras.models import load_model
# import tensorflow as tf
from google.cloud import vision

import numpy as np
import io
import gc
from datetime import datetime

import requests
import json
import configparser
import os
from urllib import parse

app = Flask(__name__, static_url_path='/static')
UPLOAD_FOLDER = 'static'
ALLOWED_EXTENSIONS = set(['pdf', 'png', 'jpg', 'jpeg', 'gif'])


config = configparser.ConfigParser()
config.read('config.ini')

## line bot api
line_bot_api = LineBotApi(config.get('line-bot', 'channel_access_token'))
handler = WebhookHandler(config.get('line-bot', 'channel_secret'))
my_line_id = config.get('line-bot', 'my_line_id')
end_point = config.get('line-bot', 'end_point')
line_login_id = config.get('line-bot', 'line_login_id')
line_login_secret = config.get('line-bot', 'line_login_secret')

# ## model
# model = load_model(config.get('model', 'model_h5'))
label = config.get('model', 'label_file')
host = config.get('REST', 'rest_host')
model = config.get('REST', 'rest_model')

## 請求 header
HEADER = {
    'Content-type': 'application/json',
    'Authorization': F'Bearer {config.get("line-bot", "channel_access_token")}'
}


## index 判斷
@app.route("/", methods=['POST', 'GET'])
def index():
    if request.method == 'GET':
        return 'ok'
    body = request.json
    events = body["events"]
    print(body)
    
    if "replyToken" in events[0]:
        payload = dict()
        replyToken = events[0]["replyToken"]
        payload["replyToken"] = replyToken       
        recordUser(events)

        if events[0]["type"] == "message":
            print()
            if events[0]["message"]["type"] == "text":
                text = events[0]["message"]["text"]                
                if text in canBrands:
                # elif text == "好味小姐":
                    brands = events[0]["message"]["text"]
                    payload["messages"] = [brandsDetail(brands)]        
                # elif text == "Hi, 我要做罐頭品牌搜尋": 
                #     payload["messages"] = [handleBransSearch()]
                # elif text == "Hi, 我要做罐頭品牌辨識": 
                #     payload["messages"] = [handleBransAnalysis()]
                # elif text == "Hi, 我要做罐頭敏感成分分析": 
                #     payload["messages"] = [handleGetAllergyRisk(),exampleAlgPhoto()]
                else:
                    payload["messages"] = [
                            {
                                "type": "text",
                                "text": text
                            }
                        ]
                replyMessage(payload)
            elif events[0]["message"]["type"] == "image":
                message_id = events[0]["message"]["id"]                
                payload["messages"] = [image_message(message_id,events)]

                replyMessage(payload)
        elif events[0]["type"] == "postback":
            pass
            postback_data = events[0]["postback"]["data"]
            if postback_data == 'flow=brandsTesxtSearch':
                payload["messages"] = [handleBransSearch()]
            elif postback_data == 'flow=brandLogoClassify':
                payload["messages"] = [handleBransAnalysis()]
            elif postback_data == 'flow=allergenAnalysis':
                payload["messages"] = [handleGetAllergyRisk()]
            else:
                pass


            replyMessage(payload)
    return 'OK'


@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)

    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def pretty_echo(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=event.message.text)
        )


## 回覆訊息
def replyMessage(payload):
    reply_url = "https://api.line.me/v2/bot/message/reply"
    response = requests.post(reply_url,
                            headers=HEADER,
                            json=payload)
    return 'OK'


## 辨識圖片
def image_message(message_id, events):
    ## 讀取圖片
    message_content = line_bot_api.get_message_content(message_id)
        
    b = b''
    for chunk in message_content.iter_content():
        b += chunk
    img = Image.open(io.BytesIO(b))

    ## 確認使用者 ostback 做對應的圖片分析
    timestamp = events[0]["timestamp"]
    sent_day = datetime.fromtimestamp(timestamp / 1000).strftime("%Y%m%d")
    user_id = events[0]["source"]["userId"]   

    with open("./user/user_record.json", "r") as f:
        user_record = json.load(f)
    
    postback_data = user_record[sent_day][user_id]["postbacks"][-1]["postback_data"]

    if postback_data == 'flow=brandLogoClassify':
        response = classify_rest(img, model,port=8501, ssl=False)
        # response = "reply brandLogoClassify"
    elif postback_data == 'flow=allergenAnalysis':
        alert_list = allergen_analysis(timestamp)
        if len(alert_list) > 0:
            alert_str = ",".join(alert_list)
            print(alert_str)
            print("發現敏感物質: ", alert_str )

            response =  "發現敏感物質:" + alert_str
        else:
            response = "未發現敏感物質"
        # response = "reply allergenAnalysis"
    else:
        response = "請從下方圖文選單選擇圖片辨識功能"
    

    # replyToken = events[0]["replyToken"]
    # line_bot_api.reply_message(
    #     replyToken,
    #     TextSendMessage(text=r))

    message = {
        "type": "text",
        "text": response
    }
    return message

def allergen_analysis(timestamp):
    YOUR_SERVICE = './gcp/gcpai.json'
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = YOUR_SERVICE
    client = vision.ImageAnnotatorClient()

    PIC = './static/user_image/' + str(timestamp) + '.jpg'
    with open(PIC, 'rb') as image_file:
        content = image_file.read()
    
    image = vision.Image(content=content)

    response = client.document_text_detection(image=image)
    texts = response.text_annotations
    ans = texts[0].description.replace("\n", "")
    print(ans)

    substrings = ["甲苯醌", "天然香料", "卡拉膠", "鹿角菜膠", "角叉菜膠", "瓜爾豆膠" , "關華豆膠", "黃原膠", "三仙膠", "玉米糖膠",
                  "馬鈴薯",  "蕃薯", "木薯", "鷹嘴豆",  "豌豆",  "青豆",  "扁豆",
                  "K3", "丁基醚", "丁基羥基茴香醚" , "BHA" , "二丁基羥甲苯", "BHT", "三羥苯甲酸丙酯", "丙基棓酸鹽", "丙二醇", "乙氧基喹啉", "乙氧基喹因", "亞硝酸鈉",
                  "玉米", "小麥", "大豆",  "糙米",  "燕麥",  "大米",  "大麥",  "粟米", "黃豆",  "釀造大米",  "啤酒酵母"]
    alert_list = []

    for s in substrings:
        if s in ans:
            # print(s)
            alert_list.append(s)
        else:
            pass
    return alert_list

def classify_rest(img, model, port=8501, ssl=False):
    res = 448
    rest = f'http{"s" if ssl else ""}://{host}:{port}/v1/models/{model}:predict'

    img = ImageOps.fit(img, (res, res))
    img = np.expand_dims(img, axis=0)/255.

    headers = {"content-type": "application/json"}
    data = json.dumps({"instances": img.tolist()})
    r = requests.post(rest, headers=headers, data=data)
    p = np.argmax(r.json()['predictions'])

    with open(label, encoding='utf-8') as f:
        # labels = f.read().split()
        labels = f.readlines()

    brands = labels[p].replace("\n", "")
    print(brands)
    return brands if 0 <= p < len(labels) else 'unknown'

## 選單功能
def handleBransSearch():
    message = {
        "type": "flex",
        "altText": "請選擇想要分析的貓罐頭品牌：",
        "contents": {
        "type": "carousel",
        "contents": [
            {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                {
                    "type": "text",
                    "text": "brands analysis",
                    "weight": "bold",
                    "color": "#FBF8F5",
                    "size": "sm"
                },
                {
                    "type": "text",
                    "text": "品牌文字搜尋",
                    "weight": "bold",
                    "size": "xl",
                    "margin": "md",
                    "color": "#FBF8F5"
                }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                {
                    "type": "text",
                    "text": "Hi, 我們目前收錄了共 20 種的貓罐頭品牌，請從下方選出想要分析的貓罐頭：",
                    "size": "sm",
                    "color": "#aaaaaa",
                    "wrap": True
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "xxl",
                    "spacing": "sm",
                    "contents": [
                    {
                        "type": "separator",
                        "margin": "none"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Lady flavor 好味小姐",
                        "data": "flow=brandsDetailSearch&brands=Lady flavor 好味小姐",
                        "displayText": "Lady flavor 好味小姐"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Dogcatstar 汪喵星球",
                        "data": "flow=brandsDetailSearch&brands=Dogcatstar 汪喵星球",
                        "displayText": "Dogcatstar 汪喵星球"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Litomon 怪獸部落",
                        "data": "flow=brandsDetailSearch&brands=Litomon 怪獸部落",
                        "displayText": "Litomon 怪獸部落"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Carnic Maniac 肉食控",
                        "data": "flow=brandsDetailSearch&brands=Carnic Maniac 肉食控",
                        "displayText": "Carnic Maniac 肉食控"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Catpool 貓侍",
                        "data": "flow=brandsDetailSearch&brands=Catpool 貓侍",
                        "displayText": "Catpool 貓侍"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "separator",
                        "margin": "none"
                    }
                    ],
                    "action": {
                    "type": "postback",
                    "label": "action",
                    "data": "hello"
                    }
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "md",
                    "contents": [
                    {
                        "type": "text",
                        "text": "〖貓咪罐罐調查局〗將為您列出品牌罐頭的各口味營養比例及敏感成分分析，希望透過此分析可以讓您選擇到最合適的貓咪罐頭。",
                        "size": "xs",
                        "color": "#aaaaaa",
                        "flex": 0,
                        "wrap": True
                    },
                    {
                        "type": "text",
                        "text": "#743289384279",
                        "color": "#aaaaaa",
                        "size": "xs",
                        "align": "end"
                    }
                    ]
                }
                ],
                "backgroundColor": "#FBF8F5"
            },
            "styles": {
                "header": {
                "backgroundColor": "#C9B0A7",
                "separator": False
                }
            }
            },
            {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                {
                    "type": "text",
                    "text": "brands analysis",
                    "weight": "bold",
                    "color": "#FBF8F5",
                    "size": "sm"
                },
                {
                    "type": "text",
                    "text": "品牌文字搜尋",
                    "weight": "bold",
                    "size": "xl",
                    "margin": "md",
                    "color": "#FBF8F5"
                }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                {
                    "type": "text",
                    "text": "Hi, 我們目前收錄了共 20 種的貓罐頭品牌，請從下方選出想要分析的貓罐頭：",
                    "size": "sm",
                    "color": "#aaaaaa",
                    "wrap": True
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "xxl",
                    "spacing": "sm",
                    "contents": [
                    {
                        "type": "separator",
                        "margin": "none"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Fantastic 超越汪喵",
                        "data": "flow=brandsDetailSearch&brands=Fantastic 超越汪喵",
                        "displayText": "Fantastic 超越汪喵"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Farmina 法米納",
                        "data": "flow=brandsDetailSearch&brands=Farmina 法米納",
                        "displayText": "Farmina 法米納"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Feline Natural K9 鮮燉",
                        "data": "flow=brandsDetailSearch&brands=Feline Natural K9 鮮燉",
                        "displayText": "Feline Natural K9 鮮燉"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Halo 嘿囉",
                        "data": "flow=brandsDetailSearch&brands=Halo 嘿囉",
                        "displayText": "Halo 嘿囉"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Healthy Shores 健康海岸",
                        "data": "flow=brandsDetailSearch&brands=Healthy Shores 健康海岸",
                        "displayText": "Healthy Shores 健康海岸"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "separator",
                        "margin": "none"
                    }
                    ],
                    "action": {
                    "type": "postback",
                    "label": "action",
                    "data": "hello"
                    }
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "md",
                    "contents": [
                    {
                        "type": "text",
                        "text": "〖貓咪罐罐調查局〗將為您列出品牌罐頭的各口味營養比例及敏感成分分析，希望透過此分析可以讓您選擇到最合適的貓咪罐頭。",
                        "size": "xs",
                        "color": "#aaaaaa",
                        "flex": 0,
                        "wrap": True
                    },
                    {
                        "type": "text",
                        "text": "#743289384279",
                        "color": "#aaaaaa",
                        "size": "xs",
                        "align": "end"
                    }
                    ]
                }
                ],
                "backgroundColor": "#FBF8F5"
            },
            "styles": {
                "header": {
                "backgroundColor": "#C9B0A7",
                "separator": False
                }
            }
            },
            {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                {
                    "type": "text",
                    "text": "brands analysis",
                    "weight": "bold",
                    "color": "#FBF8F5",
                    "size": "sm"
                },
                {
                    "type": "text",
                    "text": "品牌文字搜尋",
                    "weight": "bold",
                    "size": "xl",
                    "margin": "md",
                    "color": "#FBF8F5"
                }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                {
                    "type": "text",
                    "text": "Hi, 我們目前收錄了共 20 種的貓罐頭品牌，請從下方選出想要分析的貓罐頭：",
                    "size": "sm",
                    "color": "#aaaaaa",
                    "wrap": True
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "xxl",
                    "spacing": "sm",
                    "contents": [
                    {
                        "type": "separator",
                        "margin": "none"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Hoorooroo 厚肉肉",
                        "data": "flow=brandsDetailSearch&brands=Hoorooroo 厚肉肉",
                        "displayText": "Hoorooroo 厚肉肉"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Instinct 原點",
                        "data": "flow=brandsDetailSearch&brands=Instinct 原點米納",
                        "displayText": "Instinct 原點"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Joy food 極貓道",
                        "data": "flow=brandsDetailSearch&brands=Joy food 極貓道",
                        "displayText": "Joy food 極貓道"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Kakato 卡格",
                        "data": "flow=brandsDetailSearch&brands=Kakato 卡格",
                        "displayText": "Kakato 卡格"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "PawPawLand 肉球世界",
                        "data": "flow=brandsDetailSearch&brands=PawPawLand 肉球世界",
                        "displayText": "PawPawLand 肉球世界"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "separator",
                        "margin": "none"
                    }
                    ],
                    "action": {
                    "type": "postback",
                    "label": "action",
                    "data": "hello"
                    }
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "md",
                    "contents": [
                    {
                        "type": "text",
                        "text": "〖貓咪罐罐調查局〗將為您列出品牌罐頭的各口味營養比例及敏感成分分析，希望透過此分析可以讓您選擇到最合適的貓咪罐頭。",
                        "size": "xs",
                        "color": "#aaaaaa",
                        "flex": 0,
                        "wrap": True
                    },
                    {
                        "type": "text",
                        "text": "#743289384279",
                        "color": "#aaaaaa",
                        "size": "xs",
                        "align": "end"
                    }
                    ]
                }
                ],
                "backgroundColor": "#FBF8F5"
            },
            "styles": {
                "header": {
                "backgroundColor": "#C9B0A7",
                "separator": False
                }
            }
            },
            {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                {
                    "type": "text",
                    "text": "brands analysis",
                    "weight": "bold",
                    "color": "#FBF8F5",
                    "size": "sm"
                },
                {
                    "type": "text",
                    "text": "品牌文字搜尋",
                    "weight": "bold",
                    "size": "xl",
                    "margin": "md",
                    "color": "#FBF8F5"
                }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                {
                    "type": "text",
                    "text": "Hi, 我們目前收錄了共 20 種的貓罐頭品牌，請從下方選出想要分析的貓罐頭：",
                    "size": "sm",
                    "color": "#aaaaaa",
                    "wrap": True
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "xxl",
                    "spacing": "sm",
                    "contents": [
                    {
                        "type": "separator",
                        "margin": "none"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Weruva 唯美味",
                        "data": "flow=brandsDetailSearch&brands=Weruva 唯美味",
                        "displayText": "Weruva 唯美味"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "Ziwi Peak 巔峰",
                        "data": "flow=brandsDetailSearch&brands=Ziwi Peak 巔峰",
                        "displayText": "Ziwi Peak 巔峰"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "hojja 賀家",
                        "data": "flow=brandsDetailSearch&brands=hojja 賀家",
                        "displayText": "hojja 賀家"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "nu4PET 陪心寵糧",
                        "data": "flow=brandsDetailSearch&brands=nu4PET 陪心寵糧",
                        "displayText": "nu4PET 陪心寵糧"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "button",
                        "action": {
                        "type": "postback",
                        "label": "trilogy 奇境",
                        "data": "flow=brandsDetailSearch&brands=trilogy 奇境",
                        "displayText": "trilogy 奇境"
                        },
                        "margin": "none",
                        "color": "#8E7A4D"
                    },
                    {
                        "type": "separator",
                        "margin": "none"
                    }
                    ],
                    "action": {
                    "type": "postback",
                    "label": "action",
                    "data": "hello"
                    }
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "md",
                    "contents": [
                    {
                        "type": "text",
                        "text": "〖貓咪罐罐調查局〗將為您列出品牌罐頭的各口味營養比例及敏感成分分析，希望透過此分析可以讓您選擇到最合適的貓咪罐頭。",
                        "size": "xs",
                        "color": "#aaaaaa",
                        "flex": 0,
                        "wrap": True
                    },
                    {
                        "type": "text",
                        "text": "#743289384279",
                        "color": "#aaaaaa",
                        "size": "xs",
                        "align": "end"
                    }
                    ]
                }
                ],
                "backgroundColor": "#FBF8F5"
            },
            "styles": {
                "header": {
                "backgroundColor": "#C9B0A7",
                "separator": False
                }
            }
            }
        ]
        }
    }

    # message = {
    #         "type": "text",
    #         "text": brands_flex
    # }
    return message

def handleBransAnalysis():
    message = {
        "type": "text", 
        "text": "請拍照或提供貓罐頭 Logo 照片",
        "quickReply": photoQuickReply
    }

    return message
def handleGetNutritionInfo():
    message = {
        "type": "text",
        "text": "請拍照或提供貓罐頭成分照片，範例照片如下：",
        "quickReply": photoQuickReply
    }
    return message
def handleGetAllergyRisk():
    message = {
        "type": "text",
        "text": "請拍照或提供貓罐頭成分照片，範例照片如下：",
        "quickReply": photoQuickReply
    }
    return message


## 回覆格式
photoQuickReply = {           
            "items":
                [
                    {
                        "type": 'action',
                        "action": {
                            "type": 'cameraRoll',
                            "label": '傳送照片',
                        },
                    },
                    {
                        "type": 'action',
                        "action": {
                            "type": 'camera',
                            "label": '拍照',
                        },
                    },
                ]
        }
canBrands=[
    "巔峰",
    "鮮燉",
    "原點",
    "寵物健康",
    "唯美味",
    "嘿囉",
    "法米納",
    "汪喵星球",
    "怪獸部落",
    "好味小姐",
    "貓侍",
    "陪心寵糧",
    "肉食控",
    "極貓道",
    "自然食",
    "小玉",
    "厚肉肉",
    "超越顛峰",
    "健康海岸",
    "超越汪喵",
    "卡比",
    "肉球世界",
    "卡格",
    "賀家",
    "奇境",
    "第一饗宴",
    "超級sp"
]


def exampleNuPhoto():
    nuPhotoUrl=F"{end_point}/static/LadyFlavor_a.jpeg"
    message ={
        "type": "image",
        "originalContentUrl": nuPhotoUrl,
        "previewImageUrl": nuPhotoUrl
    }
    return message
def exampleAlgPhoto():
    algPhotoUrl=F"{end_point}/static/LadyFlavor_b.jpeg"
    message ={
        "type": "image",
        "originalContentUrl": algPhotoUrl,
        "previewImageUrl": algPhotoUrl
    }
    return message

def recordUser(events):
    try:
        with open("./user/user_record.json", "r") as f:
            user_record = json.load(f)
    except FileNotFoundError:
        user_record = {}

    timestamp = events[0]["timestamp"]
    sent_day = datetime.fromtimestamp(timestamp / 1000).strftime("%Y%m%d")
    user_id = events[0]["source"]["userId"]
    user_name = line_bot_api.get_profile(user_id).display_name

    print("sent_day:", sent_day)
    print("user_id:",user_id)
    print("user_name:",user_name)

    if sent_day not in user_record:
        user_record[sent_day]={
            user_id:{
                "user_id": user_id,
                "user_name":user_name,
                "messages":[],
                "postbacks":[]
            }
        }
            
    else:
        if  user_id not in user_record[sent_day] :
            user_record[sent_day][user_id] = {
                "user_id": user_id,
                "user_name":user_name,
                "messages":[],
                "postbacks":[]
            }
        else: 
            pass
    
    date_time = datetime.fromtimestamp(timestamp / 1000).strftime("%Y.%m.%d %H:%M")
    messages_idr = user_id[0:4]+str(timestamp)

    print("date_time:",date_time)
    print("messages_idr:",messages_idr)
    
    if events[0]["type"] == "message":
        message_id = events[0]["message"]["id"]
        if events[0]["message"]["type"] == "text":
            message_type = "text"
            text = events[0]["message"]["text"]
            print("message_type:",message_type)
            print("text:",text)

            message = {
                'id': messages_idr,
                'date_time': date_time,
                'message_id': message_id,
                'message_type': message_type,
                'text': text
            }

        elif events[0]["message"]["type"] == "image":
            message_type = "image"
            image_content = line_bot_api.get_message_content(message_id)
            
            path='./static/user_image/' + str(timestamp) + '.jpg'
            with open(path, 'wb') as fd:
                for chunk in image_content.iter_content():
                    fd.write(chunk)
            image_url = end_point +'/static/user_image/' + str(timestamp) + '.jpg'
            print("message_type:",message_type)
            print("image_url:",image_url)

            message = {
                'id': messages_idr,
                'date_time': date_time,
                'message_id': message_id,
                'message_type': message_type,
                'image_url': image_url
            }

        else:
            message_type = events[0]["message"]["type"]
            print("message_type:",message_type)
            message = {
                'id': messages_idr,
                'date_time': date_time,
                'message_id': message_id,
                'message_type': message_type
            }
        user_record[sent_day][user_id]["messages"].append(message)

    elif events[0]["type"] == "postback":
        postback_data = events[0]["postback"]["data"]
        print("postback_data:", postback_data)
        postback = {
            'id': messages_idr,
            'date_time': date_time,
            'message_type': "postback",
            'postback_data': postback_data
        }
        user_record[sent_day][user_id]["postbacks"].append(postback)

    with open("./user/user_record.json", "w") as f:
        json.dump(user_record, f)


def brandsDetail(brands):
    print(brands)

    ## 樣板
    # 蛋白
    protein_box_recom=""
    protein_box_good={
                  "type": "box",
                  "layout": "baseline",
                  "spacing": "xs",
                  "contents": [
                    {
                      "type": "icon",
                      "url": "https://raw.githubusercontent.com/eirikmadland/notion-icons/master/v5/icon1/ul-check-circle.svg",
                      "offsetStart": "xs",
                      "offsetTop": "xs"
                    },
                    {
                      "type": "text",
                      "text": "蛋白",
                      "color": "#ffffff",
                      "size": "sm",
                      "flex": 0
                    },
                    {
                      "type": "text",
                      "text": "30~50%",
                      "wrap": True,
                      "color": "#ffffff",
                      "size": "sm",
                      "align": "center"
                    }
                  ],
                  "backgroundColor": "#98D98E",
                  "cornerRadius": "lg",
                  "position": "relative",
                  "margin": "sm",
                  "width": "50%",
                  "justifyContent": "flex-start"
    }
    protein_box_warning=""
    # 脂肪
    fat_box_recom=""
    fat_box_good={
                  "type": "box",
                  "layout": "baseline",
                  "spacing": "xs",
                  "contents": [
                    {
                      "type": "icon",
                      "url": "https://www.iconsdb.com/icons/preview/white/ok-xxl.png",
                      "offsetStart": "xs",
                      "offsetTop": "xs"
                    },
                    {
                      "type": "text",
                      "text": "脂肪",
                      "color": "#ffffff",
                      "size": "sm",
                      "decoration": "none",
                      "flex": 0
                    },
                    {
                      "type": "text",
                      "text": "  50~65%",
                      "wrap": False,
                      "color": "#ffffff",
                      "size": "sm",
                      "align": "center"
                    }
                  ],
                  "backgroundColor": "#98D98E",
                  "cornerRadius": "lg",
                  "position": "relative",
                  "margin": "sm",
                  "width": "50%"
    }
    fat_box_warning=""
    # 碳水
    carb_box_good={
                  "type": "box",
                  "layout": "baseline",
                  "spacing": "xs",
                  "contents": [
                    {
                      "type": "icon",
                      "url": "https://www.iconsdb.com/icons/preview/white/ok-xxl.png",
                      "offsetStart": "xs",
                      "offsetTop": "xs"
                    },
                    {
                      "type": "text",
                      "text": "碳水",
                      "color": "#ffffff",
                      "size": "sm",
                      "flex": 0
                    },
                    {
                      "type": "text",
                      "text": "10% ↓",
                      "wrap": False,
                      "color": "#ffffff",
                      "size": "sm",
                      "align": "center"
                    }
                  ],
                  "backgroundColor": "#98D98E",
                  "cornerRadius": "lg",
                  "position": "relative",
                  "margin": "sm",
                  "width": "50%"
    }
    carb_box_warning=""
    carb_box_bad=""
    # 鈣磷比
    cap_box_good= {
        "type": "box",
        "layout": "baseline",
        "spacing": "xs",
        "contents": [
        {
            "type": "icon",
            "url": "https://www.iconsdb.com/icons/preview/white/ok-xxl.png",
            "offsetStart": "xs",
            "offsetTop": "xs"
        },
        {
            "type": "text",
            "text": "鈣磷比",
            "color": "#ffffff",
            "size": "sm"
        },
        {
            "type": "text",
            "text": "30%",
            "wrap": False,
            "color": "#ffffff",
            "size": "sm"
        }
        ],
        "backgroundColor": "#98D98E",
        "cornerRadius": "lg",
        "position": "relative",
        "margin": "sm",
        "width": "50%"
    }
    # 磷含量
    p_box_good={
                  "type": "box",
                  "layout": "baseline",
                  "spacing": "xs",
                  "contents": [
                    {
                      "type": "icon",
                      "url": "https://www.iconsdb.com/icons/preview/white/ok-xxl.png",
                      "offsetStart": "xs",
                      "offsetTop": "xs"
                    },
                    {
                      "type": "text",
                      "text": "磷含量",
                      "color": "#ffffff",
                      "size": "sm",
                      "flex": 0
                    },
                    {
                      "type": "text",
                      "text": "(一般貓貓)",
                      "color": "#ffffff",
                      "size": "xxs",
                      "flex": 0
                    },
                    {
                      "type": "text",
                      "text": "125~350mg/kcal",
                      "size": "sm",
                      "color": "#ffffff",
                      "align": "center"
                    }
                  ],
                  "backgroundColor": "#98D98E",
                  "cornerRadius": "lg",
                  "position": "relative",
                  "margin": "sm",
                  "alignItems": "center"
    }
    p_box_warning_l=""
    p_box_warning_h=""
    p_box_bad=""
    plow_box_a=""
    plow_box_b=""

    bubbles = []

    with open("./database/catscan_details.json", "r") as f:
        catscan_details = json.load(f)

    brands_detail = catscan_details[brands]

    for i in range(len(brands_detail)):
        brands_name=brands
        brands_img =brands_detail[0]["brands_img"]
        
        series = brands_detail[i]
        series_name = series["series_name"]

        tag1=series["tag1"]
        tag2_c=series["tag2"]
        allergen_c=series["allergen"]

        AAFCO=series["AAFCO"]
        # me_protein=series["me比_蛋白"]
        # me_fat=series["me比_脂肪"]
        # me_carb=series["me比_碳水"]
        # me_cap=series["me比_鈣磷比"]
        # me_p=series["me比_磷含量"]

        # brands_img ="https://www.find.org.tw/attachment/knowledge/22d2de9eeb55b3c417f7cafae7ca2d7e_cover1"
        # brands_name="好味小姐"
        # series_name="雞肉"
        # tag1="主食罐"
        # tag2="幼母貓罐"
        # AAFCO_tag="符合 AAFCO 主食罐標準"
        # allergen="卡拉膠、刺槐豆、決明子"

        
        if tag2_c != "":
            tag2=series["tag2"]
        else:
            tag2=" "

        if allergen_c != "":
            allergen=series["allergen"]
        else:
            allergen="無"
        
        if AAFCO=="Yes":
            AAFCO_tag="符合 AAFCO 主食罐標準"
        else:
            AAFCO_tag=" "
                

        # # 蛋白
        # if me_protein == "50%以上":
        #     protein_box = protein_box_good
        # elif me_protein == "35~50%":
        #     protein_box = protein_box_good
        # elif me_protein == "不在35-70%內":
        #     protein_box = protein_box_good
        # else:
        #    pass

        # # 脂肪
        # if me_fat == "50%以下":
        #     fat_box = fat_box_good
        # elif me_fat == "50~65%":
        #     fat_box = fat_box_good
        # elif me_fat == "不在30-65%內":
        #     fat_box = fat_box_good
        # else:
        #    pass

        # # 碳水
        # if me_carb == "10%以下":
        #     carb_box = carb_box_good
        # elif me_carb == "10%以上":
        #     carb_box = carb_box_good
        # elif me_carb == "15%以上":
        #     carb_box = carb_box_good
        # else:
        #    pass        

        # # 鈣磷比
        # if me_cap == "1.1~1.6":
        #     cap_box = cap_box_good
        # elif me_cap == "不在1.1~1.6內":
        #     cap_box = cap_box_good
        # else:
        #    pass  

        # # 磷含量
        # if "tag2" == "低磷罐" :
        #     if me_p == "135~250mg/kcal (邁入腎貓)":
        #         p_box = p_box_good
        #     elif me_p == "80~135mg/kcal (腎貓處方)":
        #         p_box = p_box_good
        #     else:
        #         pass 
        # else:
        #     if me_p == "125~350mg/kcal":
        #         p_box = p_box_good
        #     elif me_p == "小於125mg/kcal ":
        #         p_box = p_box_good
        #     elif me_p == "大於350 mg/kcal":
        #         p_box = p_box_good
        #     elif me_p == "大於400mg/kcal":
        #         p_box = p_box_good
        #     else:
        #         pass 

        bubble = {
            "type": "bubble",
            "size": "kilo",
            "hero": {
            "type": "image",
            "url": brands_img,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover"
            },
            "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                "type": "text",
                "text": brands_name,
                "weight": "bold",
                "size": "lg"
                },
                {
                "type": "text",
                "text": series_name,
                "size": "lg"
                },
                {
                    "type": "separator",
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": tag1,
                            "color": "#aaaaaa",
                            "size": "sm",
                            "flex": 1,
                            "weight": "bold"
                        },
                        {
                            "type": "text",
                            "text": "-"+tag2,
                            "color": "#aaaaaa",
                            "size": "sm",
                            "flex": 3,
                            "weight": "regular"
                        }
                    ]
                },
                
                {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                    "type": "text",
                    "text": AAFCO_tag,
                    "size": "xxs",
                    "color": "#aaaaaa"
                    }
                ]
                },
                {
                "type": "separator",
                "margin": "md"
                },
                {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                    "type": "text",
                    "text": "營養成分分析:",
                    "size": "xxs"
                    },
                    protein_box_good,
                    fat_box_good,
                    carb_box_good,
                    cap_box_good,
                    p_box_good
                ]
                },
                {
                "type": "separator",
                "margin": "md"
                },
                {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                    "type": "text",
                    "text": "敏感成分分析:",
                    "size": "xxs"
                    },
                    {
                    "type": "box",
                    "layout": "baseline",
                    "contents": [
                        {
                        "type": "icon",
                        "url": "https://www.iconsdb.com/icons/preview/white/warning-28-xxl.png",
                        "offsetStart": "xs",
                        "offsetTop": "xs"
                        },
                        {
                        "type": "text",
                        "color": "#ffffff",
                        "size": "sm",
                        "contents": [
                            {
                            "type": "span",
                            "text": allergen
                            }
                        ],
                        "wrap": True
                        }
                    ],
                    "backgroundColor": "#aaaaaa",
                    "cornerRadius": "xs",
                    "position": "relative",
                    "spacing": "xs",
                    "margin": "sm"
                    }
                ]
                }
            ]
            },
            "styles": {
            "footer": {
                "separator": False,
                "backgroundColor": "#aaaaaa"
            }
            }
        }
        bubbles.append(bubble)
        
        # print(bubble)
        # print("----------")

    print(brands_name)
    print(brands_img)
    print(len(brands_detail))




    ## flex 內容
    bubbles_flex={
        "type": "carousel",
        "contents": bubbles
    }
    message ={
        "type": "flex",
        "altText": brands + "品牌成分分析",
        "contents": bubbles_flex
    }

    # ## 確認 flex 問題
    # with open("./flex_ck/flex_check.json", "w") as f:
    #     json.dump(bubbles_flex, f)
    
    
    # print(bubbles_flex)

    # with open("./database/catscan_flex.json", "r") as f:
    #     catscan_flex = json.load(f)

    # message ={
    #     "type": "flex",
    #     "altText": brands + "品牌成分分析",
    #     "contents": catscan_flex
    # }

    return message



if __name__ == "__main__":
    app.debug = True
    app.run()