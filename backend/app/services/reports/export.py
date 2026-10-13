"""Bounded spreadsheet exports of the same filtered read-only report."""
import base64
import csv
from io import BytesIO,StringIO
from decimal import Decimal
from datetime import datetime,date
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from app.core import time as tz
from . import build
from .common import require

LABELS={'entry':'Giriş','exit':'Çıkış','cash':'Nakit','pos':'Harici POS','bank':'Havale / EFT','mixed':'Karma','membership':'Üyelik','lesson':'Ders','product':'Ürün','collection':'Tahsilat','refund':'İade','active':'Aktif','expired':'Süresi dolmuş','frozen':'Dondurulmuş','cancelled':'İptal','pending':'Gelecek üyelik','confirmed':'Doğrulanmış','granted':'Sensör bekleniyor','rejected':'Reddedildi','booked':'Rezervasyon','attended':'Katıldı','waiting':'Bekleme','absent':'Gelmedi','late':'Geç katıldı','excused':'Mazeret','group':'Grup','private':'Özel','consumed':'Kullanıldı','reserved':'Rezerve','released':'Geri verildi'}

def safe(value):
    if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):return "'"+value
    return value

def value(item,kind):
    if item is None:return ''
    if kind=='money':return Decimal(str(item))/100
    if kind=='boolean':return 'Evet' if item else 'Hayır'
    if kind=='date':return date.fromisoformat(item[:10]).strftime('%d.%m.%Y')
    if kind=='datetime':return tz.localtime(datetime.fromisoformat(item)).strftime('%d.%m.%Y %H:%M:%S')
    return safe(LABELS.get(item,item) if isinstance(item,str) else item)

def records(data):
    context=data['context']
    yield [data['title']]
    yield ['Şube',context['branchName']]
    yield ['Tarih aralığı',value(context['from'],'date'),value(context['to'],'date'),'Europe/Istanbul']
    yield ['Para birimi','TL (TRY); tüm tutarlar TL, zamanlar Türkiye saatidir.']
    yield ['Filtreler',str(context['filters'])]
    yield ['Üretim zamanı',value(context['generatedAt'],'datetime')]
    for metric in data['metrics']:yield [metric['label'],value(metric['value'],metric['format']),metric['scope']]
    for description in data['definitions']:yield [description]
    yield []
    for name in ['table','commands']:
        if name not in data:continue
        table=data[name]
        yield ['Kayıtlar' if name=='table' else 'Tanılama talepleri',table['count']]
        yield [col['label']+(' (TL)' if col['format']=='money' else '') for col in table['columns']]
        for row in table['rows']:yield [value(cell,col['format']) for cell,col in zip(row,table['columns'])]
        yield []
    if 'connections' in data:
        yield ['Güncel cihaz bağlantısı','Son görülme','Simülasyon','Durum']
        for device in data['connections']:yield [safe(device['code']),value(device['lastSeen'],'datetime'),value(device['simulated'],'boolean'),device['status']]

def export(user,params):
    kind=params.get('format','csv');require(kind in ['csv','xlsx'],'Dışa aktarma biçimi geçersiz.')
    data=build(user,params,export=True)
    if kind=='csv':
        stream=StringIO();writer=csv.writer(stream,delimiter=';')
        for row in records(data):writer.writerow([format(item,'.2f').replace('.',',') if isinstance(item,Decimal) else safe(item) for item in row])
        content=stream.getvalue().encode('utf-8-sig')
    else:
        workbook=Workbook(write_only=True);sheet=workbook.create_sheet('FitGate Rapor')
        for index in range(1,12):sheet.column_dimensions[chr(64+index)].width=28
        for row in records(data):
            cells=[]
            for item in row:
                cell=WriteOnlyCell(sheet,value=safe(item))
                if isinstance(item,Decimal):cell.number_format='#,##0.00 "TL"'
                cells.append(cell)
            sheet.append(cells)
        buffer=BytesIO();workbook.save(buffer);content=buffer.getvalue()
    return {'filename':f"FitGate-{params.get('tab','overview')}-{data['context']['from']}-{data['context']['to']}.{kind}",'base64':base64.b64encode(content).decode()}
