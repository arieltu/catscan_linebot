import os
from google.cloud import vision, storage
import matplotlib.pyplot as plt
from PIL import Image


YOUR_SERVICE = 'gcpai.json'
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = YOUR_SERVICE
client = vision.ImageAnnotatorClient()

# # 將輸入照片儲存到GCS
# YOUR_BUCKET = 'alexwu0209'
# YOUR_PIC = '1_Ziwi Peak _a(1).jpg'

# storage_client = storage.Client()
# bucket = storage_client.bucket(YOUR_BUCKET)
# bucket.blob(YOUR_PIC).upload_from_filename(YOUR_PIC)
# image_uri = f'gs://{YOUR_BUCKET}/{YOUR_PIC}'
# source = vision.ImageSource(image_uri=image_uri)
# image = vision.Image(source=source)

# one-shot upload
YOUR_PIC = './image_test/2_K9_g_ab.jpg'

with open(YOUR_PIC, 'rb') as image_file:
    content = image_file.read()
image = vision.Image(content=content)

response = client.document_text_detection(image=image)
# im = Image.open(YOUR_PIC)
# plt.imshow(im)

# for text in response.text_annotations:
#     # print(text.description)
#     a = [(v.x, v.y) for v in text.bounding_poly.vertices]
#     a.append(a[0])
#     x, y = zip(*a)
#     plt.plot(x, y, color='blue')

# plt.show()

im = Image.open(YOUR_PIC)
get_list = []
# plt.imshow(im)

for text in response.text_annotations:
    # print(text.description)
    get = text.description
    get_list.append(get)

# print(text.description)
print(get_list)
#一次找多個敏感物質
substrings = ["蕃薯", "甲苯醌", "豌豆", "天然香料",  "膠","亞麻籽"]

found = [s for s in substrings if s in get_list]

if found:
    print("發現敏感物質")
    for s in found:
        print(s)
else:
    print("未發現敏感物質") 