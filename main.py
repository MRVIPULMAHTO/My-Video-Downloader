import os
import json
import re
import threading
import io
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image as PILImage
import yt_dlp

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.image import Image as CoreImage
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.image import Image
from kivy.uix.progressbar import ProgressBar
from kivy.graphics import Color, Rectangle
from kivy.utils import platform

# Android Download Folder Path
def get_download_folder():
    if platform == 'android':
        from android.permissions import request_permissions, Permission
        request_permissions([Permission.WRITE_EXTERNAL_STORAGE, Permission.READ_EXTERNAL_STORAGE])
        return "/sdcard/Download"
    return os.path.join(os.path.expanduser("~"), "Downloads")

URL_PATTERN = re.compile(
    r"https?://(?:www\.)?"
    r"(?:youtube\.com|youtu\.be|instagram\.com|facebook\.com|fb\.watch|"
    r"tiktok\.com|twitter\.com|x\.com|vimeo\.com|dailymotion\.com|"
    r"reddit\.com|twitch\.tv)/\S+",
    re.IGNORECASE,
)

class QueueItemWidget(BoxLayout):
    def __init__(self, title, **kwargs):
        super().__init__(orientation='vertical', size_hint_y=None, height=90, padding=5, spacing=2, **kwargs)
        
        with self.canvas.before:
            Color(0.12, 0.15, 0.22, 1)
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)

        self.title_label = Label(text=title[:45] + "...", font_size='13sp', bold=True, size_hint_y=0.4, halign='left', color=(1, 1, 1, 1))
        self.title_label.bind(size=self.title_label.setter('text_size'))
        
        self.status_label = Label(text="Status: Queued | Speed: 0 KB/s", font_size='11sp', size_hint_y=0.3, color=(0.7, 0.7, 0.7, 1))
        self.progress_bar = ProgressBar(max=100, value=0, size_hint_y=0.3)

        self.add_widget(self.title_label)
        self.add_widget(self.status_label)
        self.add_widget(self.progress_bar)

    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

class VideoDownloaderApp(App):
    def build(self):
        self.title = "Vipul's Ultimate Downloader"
        self.download_folder = get_download_folder()
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.current_video_info = None
        self.format_map = {}

        root = BoxLayout(orientation='vertical', padding=10, spacing=10)

        # Header
        header = Label(text="🚀 Vipul's Pro Downloader", font_size='20sp', bold=True, size_hint_y=None, height=40, color=(0.38, 0.4, 0.95, 1))
        root.add_widget(header)

        # URL Input Row
        input_box = BoxLayout(orientation='horizontal', spacing=5, size_hint_y=None, height=45)
        self.url_entry = TextInput(hint_text="Paste Video Link Here...", multiline=False, size_hint_x=0.7)
        fetch_btn = Button(text="🔍 Fetch", size_hint_x=0.3, background_color=(0.38, 0.4, 0.95, 1))
        fetch_btn.bind(on_press=self.fetch_video_info)
        
        input_box.add_widget(self.url_entry)
        input_box.add_widget(fetch_btn)
        root.add_widget(input_box)

        # Info Card (Thumbnail + Title + Quality)
        self.thumb_img = Image(size_hint_y=None, height=140)
        root.add_widget(self.thumb_img)

        self.title_display = Label(text="Video details yahan dikhengi...", font_size='12sp', size_hint_y=None, height=30, color=(0.8, 0.8, 0.8, 1))
        root.add_widget(self.title_display)

        q_box = BoxLayout(orientation='horizontal', spacing=5, size_hint_y=None, height=40)
        self.quality_spinner = Spinner(text="Best Quality", values=["Best Quality"], size_hint_x=0.6)
        add_queue_btn = Button(text="📥 Download", size_hint_x=0.4, background_color=(0.13, 0.77, 0.36, 1))
        add_queue_btn.bind(on_press=self.add_to_queue)
        
        q_box.add_widget(self.quality_spinner)
        q_box.add_widget(add_queue_btn)
        root.add_widget(q_box)

        # Download Queue List
        queue_label = Label(text="Active Queue:", font_size='14sp', bold=True, size_hint_y=None, height=25, halign='left')
        queue_label.bind(size=queue_label.setter('text_size'))
        root.add_widget(queue_label)

        scroll = ScrollView(size_hint=(1, 1))
        self.queue_container = GridLayout(cols=1, spacing=5, size_hint_y=None)
        self.queue_container.bind(minimum_height=self.queue_container.setter('height'))
        scroll.add_widget(self.queue_container)
        root.add_widget(scroll)

        # Status Bar
        self.status_bar = Label(text="Status: Ready", font_size='11sp', size_hint_y=None, height=20, color=(0.6, 0.6, 0.6, 1))
        root.add_widget(self.status_bar)

        # Clipboard auto-check loop
        Clock.schedule_interval(self.check_clipboard, 2.0)

        return root

    def check_clipboard(self, dt):
        try:
            clip = Clipboard.paste()
            if clip and URL_PATTERN.search(clip.strip()):
                if self.url_entry.text != clip.strip():
                    self.url_entry.text = clip.strip()
                    self.status_bar.text = "Status: Clipboard link detected!"
        except Exception:
            pass

    def fetch_video_info(self, instance):
        url = self.url_entry.text.strip()
        if not url:
            self.status_bar.text = "Status: Pehle link daal bhai!"
            return

        self.status_bar.text = "Status: Fetching Video Info..."
        threading.Thread(target=self._async_fetch, args=(url,), daemon=True).start()

    def _async_fetch(self, url):
        try:
            ydl_opts = {"quiet": True, "noplaylist": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                self.current_video_info = info
                
                title = info.get("title", "Unknown Title")
                thumb_url = info.get("thumbnail", "")

                formats_list = ["Best Quality"]
                format_map = {"Best Quality": None}
                formats = info.get("formats", [])

                for f in formats:
                    if f.get("vcodec") != "none" and f.get("height"):
                        h = f.get("height")
                        label = f"{h}p ({f.get('ext', 'mp4')})"
                        formats_list.append(label)
                        format_map[label] = f"{f['format_id']}+bestaudio/best"

                Clock.schedule_once(lambda dt: self._update_ui_info(title, thumb_url, formats_list, format_map))
        except Exception as e:
            Clock.schedule_once(lambda dt: setattr(self.status_bar, 'text', f"Error: Fetch failed!"))

    def _update_ui_info(self, title, thumb_url, formats_list, format_map):
        self.title_display.text = title[:50] + "..."
        self.quality_spinner.values = formats_list
        self.quality_spinner.text = formats_list[0]
        self.format_map = format_map
        self.status_bar.text = "Status: Info Fetched Successfully!"

        if thumb_url:
            threading.Thread(target=self._load_thumb, args=(thumb_url,), daemon=True).start()

    def _load_thumb(self, url):
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = io.BytesIO(res.content)
                im = PILImage.open(data)
                im = im.convert('RGBA')
                
                byte_array = io.BytesIO()
                im.save(byte_array, format='PNG')
                byte_array.seek(0)

                Clock.schedule_once(lambda dt: self._set_thumb_texture(byte_array))
        except Exception:
            pass

    def _set_thumb_texture(self, byte_array):
        ci = CoreImage(byte_array, ext='png')
        self.thumb_img.texture = ci.texture

    def add_to_queue(self, instance):
        if not self.current_video_info:
            self.status_bar.text = "Status: Pehle Fetch button dabao!"
            return

        title = self.current_video_info.get("title", "Video")
        url = self.url_entry.text.strip()
        selected_q = self.quality_spinner.text
        fmt_id = self.format_map.get(selected_q)

        item_widget = QueueItemWidget(title=title)
        self.queue_container.add_widget(item_widget)

        self.executor.submit(self._download_worker, url, fmt_id, item_widget)
        self.status_bar.text = "Status: Download started!"

    def _download_worker(self, url, fmt_id, widget):
        def hook(d):
            if d['status'] == 'downloading':
                p_str = d.get('_percent_str', '0%').replace('%','').strip()
                speed = d.get('_speed_str', '0 KB/s').strip()
                try:
                    val = float(p_str)
                except ValueError:
                    val = 0
                Clock.schedule_once(lambda dt: self._update_progress(widget, val, speed))
            elif d['status'] == 'finished':
                Clock.schedule_once(lambda dt: self._mark_finished(widget))

        out_path = os.path.join(self.download_folder, "%(title)s.%(ext)s")
        ydl_opts = {
            "progress_hooks": [hook],
            "outtmpl": out_path,
            "noplaylist": True,
            "format": fmt_id if fmt_id else "best"
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            Clock.schedule_once(lambda dt: setattr(widget.status_label, 'text', 'Failed / Error!'))

    def _update_progress(self, widget, val, speed):
        widget.progress_bar.value = val
        widget.status_label.text = f"Downloading: {int(val)}% | Speed: {speed}"

    def _mark_finished(self, widget):
        widget.progress_bar.value = 100
        widget.status_label.text = "Status: Download Completed! ✅"

if __name__ == "__main__":
    VideoDownloaderApp().run()