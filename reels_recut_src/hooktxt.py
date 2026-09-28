from PIL import Image, ImageDraw, ImageFont
W,H=1080,1920
im=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)
fk=ImageFont.truetype('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',96)
fe=ImageFont.truetype('/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',62)
def c(y,t,f,fill,sw):
    w=d.textlength(t,font=f); d.text(((W-w)/2,y),t,font=f,fill=fill,stroke_width=sw,stroke_fill='black')
# pink pill behind English line
t='MOM vs. the TINY BOSS'; w=d.textlength(t,font=fe)
d.rounded_rectangle(((W-w)/2-30,250,(W+w)/2+30,340),radius=24,fill=(233,45,105,255))
d.text(((W-w)/2,258),t,font=fe,fill='white')
c(370,'엄마 vs 꼬마 술래',fk,(255,221,0,255),8)
c(490,'결국 누가 이겼을까?',ImageFont.truetype('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',70),'white',7)
im.save('hook.png')
