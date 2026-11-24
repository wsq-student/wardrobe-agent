"""Disposable desktop UI fixture; never queues model calls."""
import io
import json
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from sqlalchemy import delete
from pwdlib import PasswordHash
from app.core import session, User, Item, Conversation, Recommendation, Job, Feedback
from app import storage

def picture(color,kind='tops'):
    im=Image.new('RGB',(500,650),'#edf0e8')
    draw=ImageDraw.Draw(im)
    if kind=='bottoms': draw.polygon([(150,130),(350,130),(370,560),(275,560),(250,310),(225,560),(130,560)],fill=color)
    else: draw.polygon([(150,150),(210,115),(250,145),(290,115),(350,150),(430,310),(365,345),(330,275),(340,530),(160,530),(170,275),(135,345),(70,310)],fill=color)
    output=io.BytesIO();im.save(output,'JPEG');return output.getvalue()

if len(sys.argv)>1 and sys.argv[1]=='cleanup':
    uid=int(sys.argv[2])
    with session() as db:
        user=db.get(User,uid)
        assert user and user.email.startswith('desktop-ui-') and user.email.endswith('@wardrobe.test')
        keys=[i.image_key for i in db.query(Item).filter_by(user_id=uid)]
        keys += [j.result['image_key'] for j in db.query(Job).filter_by(user_id=uid) if j.result.get('image_key')]
        if user.profile.get('photo_key'):keys.append(user.profile['photo_key'])
        for cls in (Feedback,Job,Recommendation,Conversation,Item):db.execute(delete(cls).where(cls.user_id==uid))
        db.delete(user);db.commit()
    for key in set(keys):storage.delete(key)
    print('Disposed isolated UI fixture')
else:
    with session() as db:
        user=User(email='desktop-ui-'+uuid.uuid4().hex[:8]+'@wardrobe.test',password=PasswordHash.recommended().hash('DesktopUiCheck2026!'),profile={'city':'上海','latitude':31.2304,'longitude':121.4737,'size':'M','preferences':'简洁配色，喜欢宽松舒适的版型'})
        db.add(user);db.commit()
        items=[]
        colors=['#d6c9ac','#7692a5','#384f45','#a59880','#c4b8aa']
        for n in range(16):
            kind='bottoms' if n%3==1 else 'outerwear' if n%3==2 else 'tops'
            key=storage.save_image(user.id,picture(colors[n%len(colors)],kind))
            item=Item(user_id=user.id,name=['米白针织毛衣','蓝色直筒牛仔裤','深绿休闲外套'][n%3]+' '+str(n+1),category=kind,color=['米白','蓝色','深绿','卡其','灰色'][n%5],season=['秋','冬'],status='washing' if n==8 else 'available',image_key=key)
            db.add(item);items.append(item)
        db.flush()
        conv=Conversation(user_id=user.id,messages=[{'role':'user','content':'帮我推荐今天的通勤穿搭'},{'role':'assistant','content':json.dumps({'reason':'今天可以用米白色毛衣搭配直筒牛仔裤，再加一件深绿色外套。整体配色简洁，通勤舒适，也方便根据室内外温差调整。','clarification':'','warnings':[]},ensure_ascii=False)}])
        db.add(conv);db.flush()
        rec=Recommendation(user_id=user.id,conversation_id=conv.id,data={'item_ids':[items[0].id,items[1].id,items[2].id],'reason':'米白与蓝色搭配清爽自然，深绿外套让通勤穿搭更有层次。','clarification':'','warnings':[]})
        db.add(rec);db.flush()
        image_key=storage.save_image(user.id,picture('#739186'))
        job=Job(id=str(uuid.uuid4()),user_id=user.id,kind='tryon',status='completed',payload={'recommendation_id':rec.id},result={'image_key':image_key,'attempts':1,'review':{k:True for k in ['person_preserved','body_shape_preserved','garments_preserved','pose_preserved','no_artifacts']},'warnings':['这是一张用于页面测试的合成图片。']},trace=[{'stage':'tryon_plan','detail':'试穿计划已完成'},{'stage':'tryon_render','detail':'效果图已生成'},{'stage':'tryon_review','detail':'效果检查通过'}])
        db.add(job);db.commit()
        print(json.dumps({'id':user.id,'email':user.email,'conversation_id':conv.id,'job_id':job.id},ensure_ascii=True))
