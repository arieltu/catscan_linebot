import os
from google.cloud import vision
# import matplotlib.pyplot as plt
from PIL import Image


YOUR_SERVICE = 'gcpai.json'
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = YOUR_SERVICE
client = vision.ImageAnnotatorClient()

# one-shot upload
YOUR_PIC = './image_test/2_K9_g_ab.jpg'

with open(YOUR_PIC, 'rb') as image_file:
    content = image_file.read()
image = vision.Image(content=content)

response = client.document_text_detection(image=image)
texts = response.text_annotations
# print(texts[0].description)
ans = texts[0].description.replace("\n", "")
print(ans)

# im = Image.open(YOUR_PIC)
# plt.imshow(im)

# for text in response.text_annotations:
#     # print(text.description)
#     a = [(v.x, v.y) for v in text.bounding_poly.vertices]
#     a.append(a[0])
#     x, y = zip(*a)
#     plt.plot(x, y, color='blue')

# plt.show()

# im = Image.open(YOUR_PIC)
# plt.imshow(im)

# get_list = []
# for text in response.text_annotations:
#     # print(text.description)
#     get = text.description
#     # print(get)
#     get_list.append(get)

# print(text.description)
# print(get_list)
#一次找多個敏感物質
substrings = ["蕃薯", "甲苯醌", "豌豆", "天然香料",  "膠","亞麻籽"]

# found = [s for s in substrings if s in get_list]

# if found:
#     for s in found:
#         print(s)
#         found_list.append(s)
#     print("發現敏感物質",found_list)
# else:
#     print("未發現敏感物質") 

alert_list = []

for s in substrings:
    if s in ans:
        # print(s)
        alert_list.append(s)
    else:
        pass
    
if len(alert_list) > 0:
    print("發現敏感物質", alert_list)
else:
    print("未發現敏感物質")