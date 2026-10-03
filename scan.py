class Parser(HTMLParser):
    def __init__(self):
        super().__init__(); self.meta={}; self.scripts=[]; self.in_script=False; self.buf=[]; self.script_type=''; self.script_attrs={}
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag.lower()=='meta':
            key=d.get('property') or d.get('name'); val=d.get('content')
            if key and val:self.meta[key.lower()]=val
        if tag.lower()=='script': self.in_script=True; self.buf=[]; self.script_type=d.get('type','')
    def handle_data(self,data):
        if self.in_script:self.buf.append(data)
    def handle_endtag(self,tag):
        if tag.lower()=='script' and self.in_script:
            self.scripts.append((self.script_type,''.join(self.buf)));self.in_script=False;self.buf=[]

def valid_url(u):
    p=urlparse(u); return p.scheme in ('http','https') and p.netloc and 'tiktok.com' in p.netloc.lower()

def num_price(v):
    if isinstance(v,(int,float)): n=float(v)
    else:
        s=re.sub(r'[^0-9,.]','',str(v or ''))
        if not s:return None
        if ',' in s and '.' in s:
            s=s.replace('.','').replace(',','.') if s.rfind(',')>s.rfind('.') else s.replace(',','')
        elif '.' in s and all(len(x)==3 for x in s.split('.')[1:]):s=s.replace('.','')
        elif ',' in s and all(len(x)==3 for x in s.split(',')[1:]):s=s.replace(',','')
        try:n=float(s)
        except:return None
    return n if 100<=n<=100000000 else None

def walk(obj,out):
    if isinstance(obj,dict):
        name=price=sku=image=None
        for k,v in obj.items():
            kl=str(k).lower()
            if kl in ('name','title','productname','product_name','item_name','producttitle') and isinstance(v,(str,int,float)) and len(str(v))>2:name=str(v).strip()
            if price is None and any(t in kl for t in ('sale_price','saleprice','current_price','currentprice','min_price','minprice','price')):
                price=num_price(v)
            if kl in ('sku','productid','product_id','item_id') and v is not None:sku=str(v)
            if kl in ('image','imageurl','image_url','cover','cover_image','coverimage') and isinstance(v,str) and v.startswith(('http:','https:')):image=v
        # Schema.org Product commonly stores price inside offers/priceSpecification.
        if name and price is None:
            def find_price(x):
                if isinstance(x,dict):
                    for kk,vv in x.items():
                        kk2=str(kk).lower()
                        if kk2 in ('price','lowprice','highprice','sale_price','saleprice','current_price','currentprice'):
                            pp=num_price(vv)
                            if pp is not None:return pp
                        z=find_price(vv)
                        if z is not None:return z
                elif isinstance(x,list):
                    for vv in x:
                        z=find_price(vv)
                        if z is not None:return z
                return None
            price=find_price(obj.get('offers') or obj.get('offer') or obj.get('priceSpecification') or {})
        if name and price is not None:
            key=(name,price)
            if key not in out['seen']:
                out['seen'].add(key);out['products'].append({'name':name,'price':price,'sku':sku or '','image':image or ''})
        for v in obj.values():walk(v,out)
    elif isinstance(obj,list):
        for v in obj:walk(v,out)

def parse_page(text):
    p=Parser();p.feed(text);out={'products':[],'seen':set()}
    for typ,raw in p.scripts:
        raw=html_lib.unescape(raw).strip()
        if not raw:continue
        if 'ld+json' in typ.lower():
            try:walk(json.loads(raw),out)
            except:pass
        # Search simple product-like JSON object fragments embedded in Next/React state.
        for m in re.finditer(r'\{[^{}]{0,2500}(?:product[_ ]?name|productName|salePrice|sale_price|item_name|currentPrice|price)[^{}]{0,2500}\}',raw,re.I):
            frag=m.group(0)
            try:walk(json.loads(frag),out)
            except:pass
    title=p.meta.get('og:title') or p.meta.get('twitter:title') or 'TikTok Shop'
    return title,out['products'][:100]


from flask import Flask, request, jsonify
from urllib.request import Request, urlopen

app=Flask(__name__)

@app.post('/api/scan')
def scan():
    try:
        data=request.get_json(silent=True) or {}
        u=str(data.get('url','')).strip()
        if not valid_url(u):
            return jsonify(error='Link harus berupa URL tiktok.com.'),400
        req=Request(u,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/141 Safari/537.36','Accept-Language':'id-ID,id;q=0.9,en;q=0.8'})
        with urlopen(req,timeout=25) as r:
            text=r.read().decode('utf-8','ignore')
        store,prods=parse_page(text)
        note='Data berasal dari HTML publik.' if prods else 'Katalog produk tidak terekspos di HTML yang diterima. TikTok dapat membutuhkan rendering/login atau membatasi request.'
        return jsonify(store_name=store,products=prods,message=f'Scan selesai — {len(prods)} produk terbaca.',note=note)
    except Exception as e:
        return jsonify(error=f'Tidak bisa membaca halaman toko: {e}'),502
