"""Native tray/Tk lifecycle integration check; no device or media worker."""
import sys,json
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'desktop'))
from app import App
from tray import RESTORE_MESSAGE,CALLBACK_MESSAGE

class TestApp(App):
    def run_worker(self):self.stop.wait()

app=TestApp(SimpleNamespace(port=None,demo=True,minimized=True))
app.root.title('MacroDeck · Bildirim alanı testi')
records=[];errors=[]
def step(callback):
    try:callback()
    except BaseException as exc:
        errors.append(exc);app.close()
def restored():
    assert app.root.state()=='normal',app.root.state()
    records.append('native restore opens Tk window')
    app.window_close()
    assert app.root.state()=='withdrawn'
    assert not app.stop.is_set() and app.thread.is_alive()
    records.append('close hides window while worker continues')
    app.show_window();app.root.iconify()
    app.root.after(350,lambda:step(minimized))
def minimized():
    assert app.root.state()=='withdrawn',app.root.state()
    records.append('minimize hides to notification area')
    app.tray.user.PostMessageW(app.tray.hwnd,CALLBACK_MESSAGE,1,0x203)
    app.root.after(200,lambda:step(double_clicked))
def double_clicked():
    assert app.root.state()=='normal',app.root.state()
    records.append('tray double-click opens window')
    app.tray_events.put('exit')
def hidden():
    assert app.tray and app.tray.available
    assert app.root.state()=='withdrawn',app.root.state()
    records.append('minimized startup hides window')
    app.tray.user.PostMessageW(app.tray.hwnd,RESTORE_MESSAGE,0,0)
    app.root.after(200,lambda:step(restored))
app.root.after(200,lambda:step(hidden))
app.run()
app.thread.join(timeout=1)
if errors:raise errors[0]
assert app.stop.is_set() and not app.tray.thread.is_alive() and not app.thread.is_alive()
records.append('exit stops worker and removes notification icon')
result={'result':'PASS','checks':records}
(ROOT/'test-results').mkdir(exist_ok=True)
(ROOT/'test-results/tray.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
