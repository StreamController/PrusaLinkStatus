from functools import lru_cache
import json
import threading
import time

from matplotlib.testing import _has_tex_package
from numpy import isin
from src.backend.PluginManager.ActionBase import ActionBase
from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder
from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.ActionInputSupport import ActionInputSupport

# Import gtk modules
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio

import sys
import os
from PIL import Image
from loguru import logger as log
import requests

# Add plugin to sys.paths
sys.path.append(os.path.dirname(__file__))
from plugins.com_core447_PrusaLinkStatus.GraphBase import GraphBase

# Import globals
import globals as gl

# Import own modules
from src.backend.DeckManagement.DeckController import DeckController
from src.backend.PageManagement.Page import Page

import PrusaLinkPy #TODO: Remove, also from the app requirements

class Status(ActionBase):
    def __init__(self, action_id: str, action_name: str,
                 deck_controller: "DeckController", page: Page, coords: str, plugin_base: PluginBase):
        super().__init__(action_id=action_id, action_name=action_name,
            deck_controller=deck_controller, page=page, coords=coords, plugin_base=plugin_base)
        
    def get_config_rows(self) -> list:
        self.ip_row = Adw.EntryRow(title=self.plugin_base.lm.get("actions.status.ip.title"))
        self.key_row = Adw.PasswordEntryRow(title=self.plugin_base.lm.get("actions.status.key.title"))

        self.top_label_row = Adw.EntryRow(title=self.plugin_base.lm.get("actions.status.top-label.title"))
        self.center_label_row = Adw.EntryRow(title=self.plugin_base.lm.get("actions.status.center-label.title"))
        self.bottom_label_row = Adw.EntryRow(title=self.plugin_base.lm.get("actions.status.bottom-label.title"))

        self.load_config_defaults()

        # Connect signals
        self.ip_row.connect("notify::text", self.on_ip_row_changed)
        self.key_row.connect("notify::text", self.on_key_row_changed)
        self.top_label_row.connect("notify::text", self.on_label_row_changed)
        self.center_label_row.connect("notify::text", self.on_label_row_changed)
        self.bottom_label_row.connect("notify::text", self.on_label_row_changed)

        return [self.ip_row, self.key_row, self.top_label_row, self.center_label_row, self.bottom_label_row]
    
    def get_custom_config_area(self):
        text = "<ul> \
        <li>state</li>\
        <li>temp_bed</li> \
        <li>target_bed</li> \
        <li>temp_nozzle</li> \
        <li>target_nozzle</li> \
        <li>axiz_z</li> \
        <li>axiz_y</li> \
        <li>axiz_x</li> \
        <li>flow_</li> \
        <li>speed</li> \
        <li>progress</li> \
        <li>fan_hotend</li> \
        <li>fan_print</li> \
        <li>time_remaining</li> \
        <li>time_printing</li> \
        </ul>"
        #FIXME
        label = Gtk.Label(use_markup=True, hexpand=True, vexpand=True, wrap=True) 
        label = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD, hexpand=True, vexpand=True, css_classes=["flat"], editable=False, cursor_visible=False)
        # label.get_buffer().set_text(text)
        buffer = label.get_buffer()
        buffer.insert_markup(buffer.get_start_iter(), text, -1)
        # label.set_markup("<b>bold</b> <i>italic</i>")



        return label


    def load_config_defaults(self):
        settings = self.plugin_base.get_settings()
        ip = settings.get("ip", "")
        key = settings.get("key", "")

        settings = self.get_settings()
        top = settings.get("labels", {}).get("top", "")
        center = settings.get("labels", {}).get("center", "")
        bottom = settings.get("labels", {}).get("bottom", "")

        # Update ui
        self.ip_row.set_text(ip)
        self.key_row.set_text(key)
        self.top_label_row.set_text(top)
        self.center_label_row.set_text(center)
        self.bottom_label_row.set_text(bottom)

    def on_ip_row_changed(self, entry, *args):
        settings = self.plugin_base.get_settings()
        settings["ip"] = entry.get_text()
        self.plugin_base.set_settings(settings)

        self.plugin_base.printer.host = entry.get_text()
        self.plugin_base.data = self.plugin_base.fetch_data()

    def on_key_row_changed(self, entry, *args):
        settings = self.plugin_base.get_settings()
        settings["key"] = entry.get_text()
        self.plugin_base.set_settings(settings)

        self.plugin_base.printer.api_key = entry.get_text()
        self.plugin_base.data = self.plugin_base.fetch_data()

    def on_label_row_changed(self, entry, *args):
        settings = self.get_settings()
        settings.setdefault("labels", {})
        settings["labels"]["top"] = self.top_label_row.get_text()
        settings["labels"]["center"] = self.center_label_row.get_text()
        settings["labels"]["bottom"] = self.bottom_label_row.get_text()

        self.set_settings(settings)
        self.show()


    def on_tick(self) -> None:
        self.show()

    def show(self):
        data = self.plugin_base.data
        if data is None:
            self.set_top_label(self.plugin_base.lm.get("actions.status.errors.no-data.top"), font_size=12)
            self.set_center_label(self.plugin_base.lm.get("actions.status.errors.no-data.center"), font_size=12)
            self.set_bottom_label(None)
            return
        
        settings = self.get_settings()

        top = self.inject_data(settings.get("labels", {}).get("top", ""), data)
        center = self.inject_data(settings.get("labels", {}).get("center", ""), data)
        bottom = self.inject_data(settings.get("labels", {}).get("bottom", ""), data)

        self.set_top_label(top, font_size=14)
        self.set_center_label(center, font_size=14)
        self.set_bottom_label(bottom, font_size=14)

    
    def inject_data(self, label: str, data: dict) -> str:
        for key in data:
            value = data[key]
            if key in ["time_remaining", "time_printing"]:
                value = self.seconds_to_readable(value)

            if isinstance(value, float):
                value = round(value)
            
            label = label.replace("{" + key + "}", str(value))
        return label
    
    def seconds_to_readable(self, seconds: int) -> str:
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02d}:{minutes:02d}"
    

class HotendTemperature(GraphBase):
    def __init__(self, action_id: str, action_name: str,
                 deck_controller: "DeckController", page: Page, coords: str, plugin_base: PluginBase):
        super().__init__(action_id=action_id, action_name=action_name,
            deck_controller=deck_controller, page=page, coords=coords, plugin_base=plugin_base)
        
    def get_config_rows(self) -> list:
        super_rows = super().get_config_rows()
        self.ip_row = Adw.EntryRow(title=self.plugin_base.lm.get("actions.status.ip.title"))
        self.key_row = Adw.PasswordEntryRow(title=self.plugin_base.lm.get("actions.status.key.title"))

        self.top_label_row = Adw.EntryRow(title=self.plugin_base.lm.get("actions.status.top-label.title"))
        self.center_label_row = Adw.EntryRow(title=self.plugin_base.lm.get("actions.status.center-label.title"))
        self.bottom_label_row = Adw.EntryRow(title=self.plugin_base.lm.get("actions.status.bottom-label.title"))

        self.load_config_defaults()

        # Connect signals
        self.ip_row.connect("notify::text", self.on_ip_row_changed)
        self.key_row.connect("notify::text", self.on_key_row_changed)
        self.top_label_row.connect("notify::text", self.on_label_row_changed)
        self.center_label_row.connect("notify::text", self.on_label_row_changed)
        self.bottom_label_row.connect("notify::text", self.on_label_row_changed)

        super_rows.extend([self.ip_row, self.key_row, self.top_label_row, self.center_label_row, self.bottom_label_row])

        return super_rows
   

    def load_config_defaults(self):
        settings = self.plugin_base.get_settings()
        ip = settings.get("ip", "")
        key = settings.get("key", "")
        top = settings.get("labels", {}).get("top", "")
        center = settings.get("labels", {}).get("center", "")
        bottom = settings.get("labels", {}).get("bottom", "")

        # Update ui
        self.ip_row.set_text(ip)
        self.key_row.set_text(key)
        self.top_label_row.set_text(top)
        self.center_label_row.set_text(center)
        self.bottom_label_row.set_text(bottom)

    def on_ip_row_changed(self, entry, *args):
        settings = self.plugin_base.get_settings()
        settings["ip"] = entry.get_text()
        self.plugin_base.set_settings(settings)

        self.plugin_base.printer.host = entry.get_text()
        self.plugin_base.data = self.plugin_base.fetch_data()

    def on_key_row_changed(self, entry, *args):
        settings = self.plugin_base.get_settings()
        settings["key"] = entry.get_text()
        self.plugin_base.set_settings(settings)

        self.plugin_base.printer.api_key = entry.get_text()
        self.plugin_base.data = self.plugin_base.fetch_data()

    def on_label_row_changed(self, entry, *args):
        settings = self.get_settings()
        settings.setdefault("labels", {})
        settings["labels"]["top"] = self.top_label_row.get_text()
        settings["labels"]["center"] = self.center_label_row.get_text()
        settings["labels"]["bottom"] = self.bottom_label_row.get_text()

        self.set_settings(settings)
        self.show()


    def on_tick(self) -> None:
        if self.plugin_base.data is None:
            return
        
        temp = self.plugin_base.data.get("temp_nozzle", -1)
        target = self.plugin_base.data.get("target_nozzle", -1)
        self.target = target
        self.percentages.append(temp)

        self.show_graph()

        self.set_bottom_label(f"{temp}°C", font_size=16)


class PrusaLinkStatusPlugin(PluginBase):
    def __init__(self):
        super().__init__()

        self.init_locale_manager()
        self.init_printer()

        self.data = {}
        threading.Thread(target=self.fetch_data_loop, name="printer status fetch", daemon=True).start()

        self.lm = self.locale_manager

        ## Register actions
        self.status_holder = ActionHolder(
            plugin_base=self,
            action_base=Status,
            action_id_suffix="Status",
            action_name=self.lm.get("actions.status.name"),
            action_support={
                Input.Key: ActionInputSupport.SUPPORTED,
                Input.Dial: ActionInputSupport.SUPPORTED,
                Input.Touchscreen: ActionInputSupport.UNSUPPORTED
            }
        )
        self.add_action_holder(self.status_holder)

        self.hotend_temp_holder = ActionHolder(
            plugin_base=self,
            action_base=HotendTemperature,
            action_id_suffix="HotendTemperature",
            action_name=self.lm.get("actions.hotend-temp.name"),
            action_support={
                Input.Key: ActionInputSupport.SUPPORTED,
                Input.Dial: ActionInputSupport.SUPPORTED,
                Input.Touchscreen: ActionInputSupport.UNSUPPORTED
            }
        )
        self.add_action_holder(self.hotend_temp_holder)


        # Register plugin
        self.register(
            plugin_name=self.lm.get("plugin.name"),
            github_repo="https://github.com/StreamController/PrusaLinkStatus",
            plugin_version="1.0.0",
            app_version="1.1.1-alpha"
        )

    def init_locale_manager(self):
        self.lm = self.locale_manager
        self.lm.set_to_os_default()

    def init_printer(self):
        ip = self.get_settings().get("ip")
        key = self.get_settings().get("key")
        self.printer = PrusaLinkPy.PrusaLinkPy(ip, key)


    def fetch_data_loop(self) -> None:
        while True:
            self.data = self.fetch_data()

            time.sleep(5)

    def fetch_data(self) -> dict:
        data = {}
        try:
            status = self.printer.get_status()
        except:
            return
        

        if status.status_code != 200:
            return
        
        data.update(status.json().get("printer", {}))
        data.update(status.json().get("job", {}))
        return data

