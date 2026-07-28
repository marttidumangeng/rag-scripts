import os, requests
from PIL import Image, ImageDraw
S = requests.Session(); S.headers["User-Agent"]="Mozilla/5.0"
os.makedirs("staging/_av", exist_ok=True)
ITEMS = [
    ("519 hero", "https://cdn.robotaigeek.com/robots/original/robot_519_74c241ade0f646549fdb0cc62795cce5.jpg"),
    ("519 p1", "https://cdn.robotaigeek.com/robots/photos/robot_519_1_df9861c455c24156896ef895297d017b.jpg"),
    ("519 p2", "https://cdn.robotaigeek.com/robots/photos/robot_519_2_e28c1bfda7de4fdd82390cf8f4e1dfcb.jpg"),
    ("1509 hero(BAD webp)", "https://cdn.robotaigeek.com/robots/original/robot-1509-pro-5.webp"),
    ("1509 p1", "https://cdn.robotaigeek.com/robots/photos/photo-1509-5597.jpg"),
    ("1509 p2", "https://cdn.robotaigeek.com/robots/photos/photo-1509-5598.jpg"),
    ("1509 p3webp", "https://cdn.robotaigeek.com/robots/photos/photo-1509-5599.webp"),
    ("1509 p4webp", "https://cdn.robotaigeek.com/robots/photos/photo-1509-5600.webp"),
    ("1509 p5webp", "https://cdn.robotaigeek.com/robots/photos/photo-1509-5601.webp"),
    ("1509 p6webp", "https://cdn.robotaigeek.com/robots/photos/photo-1509-5602.webp"),
    ("1509 p7", "https://cdn.robotaigeek.com/robots/photos/photo-1509-5603.jpg"),
    ("AVINC Pro5 hero", "https://www.avinc.com/wp-content/uploads/2026/03/Product-Page_UMV_Pro-5_Hero.jpg"),
    ("shared webp 76798a", "https://cdn.robotaigeek.com/robots/photos/photo-1506-5649.webp"),
    ("1506 hero", "https://cdn.robotaigeek.com/robots/original/robot-1506-vigilanthalo.jpg"),
]
paths=[]
for label,u in ITEMS:
    try:
        g=S.get(u,timeout=30)
        if g.ok:
            ext="png"
            p="staging/_av/%s.%s"%(label.replace(" ","_").replace("(","").replace(")",""),ext)
            open(p,"wb").write(g.content); paths.append((label,p))
    except Exception as e:
        print("fail",label,str(e)[:40])
cell=300; cols=5; rows=(len(paths)+cols-1)//cols
sheet=Image.new("RGB",(cols*cell,max(rows,1)*cell),(235,235,240)); d=ImageDraw.Draw(sheet)
for i,(label,p) in enumerate(paths):
    try:
        im=Image.open(p).convert("RGB"); im.thumbnail((cell-14,cell-34))
        x=(i%cols)*cell+7; y=(i//cols)*cell+26; sheet.paste(im,(x,y)); d.text((x,y-18),label,fill=(0,0,0))
    except Exception as e:
        d.text(((i%cols)*cell+7,(i//cols)*cell+26),label+" ERR",fill=(200,0,0))
sheet.save("staging/_av/_contact.png"); print("saved", len(paths))
