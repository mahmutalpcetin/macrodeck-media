"""Local Tk layout check, with no device/media worker or system changes."""
import sys,json,argparse
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'desktop'))
from app import App
from model import Track
from rendering import render

class LayoutApp(App):
    def run_worker(self):self.stop.wait()

parser=argparse.ArgumentParser()
parser.add_argument('--show',action='store_true')
args=parser.parse_args()
app=LayoutApp(SimpleNamespace(port=None,demo=True,minimized=False,tray=False))
app.root.title('MacroDeck · Düzen testi')
sample=Track(title='İstanbul’da bir akşam — uzun video başlığı ve Türkçe karakterler '*3,
             artist='Örnek sanatçı · Ş, Ğ, İ, ı, Ö, Ü, Ç',available=True,demo=True)
app.update_track(sample);app.show_image(render(sample))
records=[]
def inspect(index=0):
    app.root.update_idletasks()
    width,height=app.root.winfo_width(),app.root.winfo_height()
    record={'window':[width,height],'preview':list(app._preview_size)}
    assert app.preview_host.winfo_width()>250,record
    assert app.preview_host.winfo_height()>160,record
    assert app.preview.winfo_width()<=app.preview_host.winfo_width(),record
    # Main controls remain inside the root; scrollable settings can exceed their canvas.
    for widget in (app.preview_host,app.source_combo,app.port_box):
        assert widget.winfo_rootx()+widget.winfo_width()<=app.root.winfo_rootx()+width,record
    records.append(record)
    if index==0:
        app.root.geometry('940x640');app.root.after(300,lambda:inspect(1))
    else:
        print(json.dumps({'result':'PASS','layouts':records},indent=2),flush=True)
        if not args.show:app.close()
app.root.after(300,inspect)
app.run()
