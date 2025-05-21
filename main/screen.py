from datetime import datetime
from msilib.schema import Error
import multiprocessing
from sqlite3 import connect
import time
import tkinter as tk
from tkinter import filedialog as fd
from tkinter import messagebox as mb
from tkinter import ttk
import subprocess
import psutil
import socket
import paramiko
import re
import detection
import threading
import sys
from ttkthemes import ThemedTk
import cv2 
import ctypes
import ttkthemes
import tkinter.font as tkfont
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  
except Exception:
    pass
def is_ethernet_connected():
    net_if_addrs = psutil.net_if_addrs()
    net_if_stats = psutil.net_if_stats()
    for iface, stats in net_if_stats.items():
        if stats.isup and "Ethernet" in iface:
            return True
    return False
def is_pi_reachable(hostname="raspberrypi.local"):
    try:
        output = subprocess.check_output(["ping", "-n", "1", hostname], timeout=3)
        return True
    except subprocess.CalledProcessError:
        return False
    except subprocess.TimeoutExpired:
        return False
def resolve_pi_ip(hostname="raspberrypi.local"):
    try:
        ip = socket.gethostbyname(hostname)
        return ip
    except socket.gaierror:
        return None
def try_connecting_to_pi(username,password):
    if is_ethernet_connected():
        if is_pi_reachable():
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(hostname="raspberrypi.local", username=username, password=password, timeout=5)
                return "Connected"
            except paramiko.AuthenticationException:
                return "Authentication failed."
            except paramiko.SSHException as sshException:
                return (f"Unable to establish SSH connection: {sshException}")
            except Exception as e:
                return (f" Connection failed: {e}")
            finally:
                client.close()
        else:
            return 'Pi is unreacahable.'       
    else:
       return "Ethernet is not connected."    
class App(ThemedTk):
    def __init__(self):
        super().__init__()
        self.geometry('800x600')
        self.set_theme('breeze')
        style=ttk.Style(self)
        style.configure(".", font=("Tahoma", 14))
        self.dt_and_s= detection.object_detect_and_send()
        self.event=threading.Event()
        self.event.set()
        self.folder_path=""
        self.password=""
        self.selected_mac=''
        self.obex_channel=''
        self.mac_page=None
        self.macs=set()
        self.title("Smart Office Security System")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        container = ttk.Frame(self)
        container.pack(expand=True,fill='both')
        self.pages = {}
        for PageClass in (StartPage,): 
            page = PageClass(container, self)
            self.pages[PageClass] = page
            page.pack(expand=True,fill='both')
        self.show_page(StartPage)
    def on_close(self):
        self.event.clear()
        self.destroy()
        sys.exit(0)


    def browse_folder(self,folder_entry):
        folder_path = fd.askdirectory()  
        if folder_path:  
            folder_entry.delete(0, tk.END)  
            folder_entry.insert(0, folder_path)
    def show_page(self, page_class):
        page = self.pages[page_class]
        page.tkraise()
    def on_send_button_click(self, folder_entry, password_entry):
        folder = folder_entry.get()
        password = password_entry.get()
        if not folder or not password:
            mb.showwarning("Missing Info", "Please enter the output folder and Raspberry Pi password.")
            return
        self.folder_path = folder
        self.password = password
        container = self.pages[StartPage].master
        second_page = SecondPage(container, self)
        self.pages[SecondPage] = second_page
        self.pages[StartPage].pack_forget()
        second_page.pack(expand=True,fill='both')
        self.show_page(SecondPage)
    def get_mac_addresses(self):
        client=paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if(len(self.password)>0):
            try:
                client.connect('raspberrypi.local', username='admin', password=self.password)
                channel=client.invoke_shell()
                channel.send("bluetoothctl\n")
                channel.send("power on\n")
                channel.send("agent on\n")
                channel.send("scan on\n")
                buffer = ""
                while self.pages[ThirdPage].load_mac_addr_event.is_set(): 
                    if channel.recv_ready():
                        data = channel.recv(1024).decode("utf-8")
                        buffer += data
                        lines = buffer.split("\n")
                        buffer = lines[-1]
                        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                        for line in lines[:-1]:
                            line = ansi_escape.sub('', line)
                            line = ''.join(ch for ch in line if ch.isprintable())
                            line= line.strip()
                            if '[NEW] Device' in line or '[CHG] Device' in line:
                                mac=line.split()[3]
                                self.macs.add(mac)
                            elif '[DEL] Device' in line:
                                mac=line.split()[3]
                                self.macs.discard(mac)
                            self.pages[ThirdPage].update_listbox(self.macs)    

                channel.send("scan off\n")
                channel.send("exit\n")
                channel.close()
            finally:
                client.close()
    def set_obex_channel(self):
        cmd = f'sdptool browse {self.selected_mac}'
        client=paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        output=''
        if(len(self.password)>0):
            try:
                client.connect('raspberrypi.local', username='admin', password=self.password)
                stdin, stdout, stderr = client.exec_command(cmd)
                lines = stdout.read().decode().splitlines()
                obex_found=False
                for line in lines:
                    if(obex_found):
                        if(line.find('Channel')!=-1):
                            output=line.split(':')[1].strip()
                            break
                    else:
                        if(line.find('OBEX')!=-1):
                            obex_found=True            
            finally:
                client.close()
            self.obex_channel=output
            self.pages[ThirdPage].obex_event.set()
    def set_bluetooth_connection(self):
        get_cnct_bt='cat expect.sh'
        client=paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        output=''
        if(len(self.password)>0):
            try:
                client.connect('raspberrypi.local', username='admin', password=self.password)
                remove_command=f'remove {self.selected_mac}'
                stdin,stdout,stderr=client.exec_command(f'bluetoothctl {remove_command}')
                output=stdout.read().decode()
                client.exec_command('clear')
                stdin,stdout,stderr=client.exec_command(get_cnct_bt)
                script=stdout.read().decode()
                script = script.replace('MAC', self.selected_mac)
                script_escaped = script.replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')
                remote_write_command = f'echo "{script_escaped}" > temp_expect.sh && chmod +x temp_expect.sh'
                client.exec_command(remote_write_command)
                stdin, stdout, stderr = client.exec_command('expect ./temp_expect.sh')
                output = stdout.read().decode()
                errors = stderr.read().decode()
            finally:
                client.close()
            self.pages[ThirdPage].bt_setup_event.set()
            return output    
        
class StartPage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.pack(expand=True,fill='both')
        self.controller = controller

        folder_label = ttk.Label(self, text="Select Output Folder:",font=("Tahoma", 14))
        folder_label.pack(expand=True,fill='both',pady=5)

        self.folder_entry = ttk.Entry(self, width=40,font=("Tahoma", 14))
        self.folder_entry.pack(expand=True,fill='both',pady=5)

        browse_button = ttk.Button(self, text="Browse", command=lambda: controller.browse_folder(self.folder_entry))
        browse_button.pack(expand=True,fill='both',pady=5)

        password_label = ttk.Label(self, text="Enter Raspberry Pi Password:",font=("Tahoma", 14))
        password_label.pack(expand=True,fill='both',pady=5)

        self.password_entry = ttk.Entry(self, show="*", width=40,font=("Tahoma", 14))
        self.password_entry.pack(expand=True,fill='both',pady=5)

        continue_button = ttk.Button(
            self,
            text="Continue",
            command=self.on_continue_click
        )
        continue_button.pack(expand=True,fill='both',pady=20)
        continue_button.bind('<Return>',lambda event:self.on_continue_click())

    def on_continue_click(self):
        folder = self.folder_entry.get()
        password = self.password_entry.get()

        if not folder or not password:
            mb.showwarning("Missing Info", "Please enter the folder and password.")
            return

        self.controller.folder_path = folder
        self.controller.password = password
        container = self.controller.pages[StartPage].master  
        second_page = SecondPage(container, self.controller)
        self.controller.pages[SecondPage] = second_page
        second_page.pack(expand=True,fill='both')
        self.controller.pages[StartPage].pack_forget()
        self.controller.show_page(SecondPage)
class SecondPage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.pack(expand=True,fill='both')
        self.controller = controller
        self.text_label = ttk.Label(self, text="Ready to connect to Raspberry Pi...",font=("Tahoma", 14))
        self.text_label.pack(expand=True,fill='both',pady=10)

        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.pack(expand=True,fill='both',pady=5)

        self.connect_button = ttk.Button(self, text="Connect Now", command=self.start_connection_thread)
        self.connect_button.pack(expand=True,fill='both',pady=10)
    def start_connection_thread(self):
        self.progress.start()
        threading.Thread(target=self.try_connect_async, daemon=True).start()

    def try_connect_async(self):
        try:
            result = try_connecting_to_pi(username="admin", password=self.controller.password)
            self.after(0, lambda: self.handle_result(result))
        except Exception as e:
            self.after(0, lambda: self.text_label.config(text=f"Error: {e}"))


    def handle_result(self, result):
        self.progress.stop()
        self.progress.pack_forget()
        if result == "Connected":
            self.text_label.config(text="Connected successfully!")
            container = self.controller.pages[StartPage].master
            third_page = ThirdPage(container, self.controller)
            self.controller.pages[ThirdPage] = third_page
            self.controller.pages[SecondPage].pack_forget()
            third_page.pack(expand=True,fill='both')
            self.after(2000, lambda: self.controller.show_page(ThirdPage))
        elif result == "Authentication failed.":
            self.text_label.config(text="Authentication failed. Please try again.")
            password_label = ttk.Label(self, text="Enter Raspberry Pi Password:",font=("Tahoma", 14))
            password_label.pack(expand=True,fill='both',pady=5)
            self.password_entry = ttk.Entry(self, show="*", width=40,font=("Tahoma", 14))
            self.password_entry.pack(expand=True,fill='both',pady=5)
            self.connect_button.configure(text='Retry',command=self.retry_with_new_password)
        else:
            self.text_label.config(text="Could not connect. Try again?")
            self.connect_button.configure(text='Retry',command=self.start_connection_thread)

    def retry_with_new_password(self):
        self.controller.password = self.password_entry.get()
        self.start_connection_thread()
class ThirdPage(ttk.Frame):   
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.pack(expand=True,fill='both')
        self.controller = controller
        self.controller.mac_page=self
        self.build_ui()
    def build_ui(self):
            self.text_label = ttk.Label(self, text='Retrieving available MAC addresses...',font=("Tahoma", 14))
            self.text_label.pack(expand=True,fill='both',pady=5)
            self.listbox=tk.Listbox(self,selectmode='single',font=("Tahoma", 14))
            self.listbox.pack(expand=True,fill='both',pady=10)
            self.confirm_button = ttk.Button(self, text='Confirm selection', command=self.confirm_selection,state='disabled')
            self.confirm_button.pack(expand=True,fill='both',pady=5)
            try:
                threading.Thread(target=self.load_mac_addresses, daemon=True).start()
            except Exception as e:
                print(e)
    def update_listbox(self,macs):
        self.listbox.delete(0,tk.END)
        for mac in macs:
            self.listbox.insert(tk.END,mac)
        if not macs:
            self.listbox.insert(tk.END,'There is not any available device')
            self.confirm_button.configure(state='disabled')
        else:
            self.text_label.config(text="Select a device:")
            self.confirm_button.configure(state='active')
    def load_mac_addresses(self):
            self.load_mac_addr_event=threading.Event()
            self.load_mac_addr_event.set()
            self.controller.get_mac_addresses()
        
    def confirm_selection(self):
        if self.listbox.curselection():
            selected = self.listbox.get(self.listbox.curselection())
            self.controller.selected_mac = selected
            self.load_mac_addr_event.clear()
            threading.Thread(target=self.setup_bluetooth_connection, daemon=True).start()
        else:
            mb.showwarning(message='You have not selected any MAC address.')
    def setup_bluetooth_connection(self):
        self.obex_event=threading.Event()
        self.text_label.configure(text=f'Getting the obex channel..')
        self.listbox.destroy()
        self.confirm_button.destroy()
        self.pg_bar=ttk.Progressbar(self,mode='indeterminate')
        self.pg_bar.pack(expand=True,fill='both',pady=5)
        self.pg_bar.start()
        self.controller.set_obex_channel()
        self.obex_event.wait()
        self.pg_bar.stop()
        self.pg_bar['value']=0
        self.bt_setup_event=threading.Event()
        self.text_label.configure(text=f'Got the obex channel. Setting up the bluetooth connection...')
        self.pg_bar.start()
        self.controller.set_bluetooth_connection()
        self.bt_setup_event.wait()
        self.pg_bar.destroy()
        self.text_label.configure(text='Bluetooth connection set. Going to the next page..')
        container = self.controller.pages[StartPage].master
        last_page = LastPage(container, self.controller)
        self.controller.pages[LastPage] = last_page
        self.controller.pages[ThirdPage].pack_forget()
        last_page.pack(expand=True,fill='both')
        self.after(3000, lambda: self.controller.show_page(LastPage))

class LastPage(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.pack(expand=True,fill='both')
        self.controller = controller
        self.scr_n_dtct_event=threading.Event()
        self.script_run=threading.Event()
        self.build_ui()
        self.frame_queue1=multiprocessing.Queue()
        self.frame_queue2=multiprocessing.Queue()
    def build_ui(self):
            self.ready_txt = ttk.Label(self, text='Everything is ready!',font=("Tahoma", 14))
            self.ready_txt.pack(expand=True,fill='both',pady=10)
            self.progress = ttk.Progressbar(self, mode='indeterminate')
            self.progress.pack(expand=True,fill='both',pady=10)
            self.progress.stop()       
            self.status_label = ttk.Label(self, text='')
            self.status_label.pack(expand=True,fill='both',pady=5)
            self.start_button = ttk.Button(self, text='Start', command=self.on_start_button_click)
            self.start_button.pack(expand=True,fill='both',pady=5)
    def on_start_button_click(self):
        self.progress.start()
        self.status_label.config(text="Connecting to Raspberry Pi and running script...")
        self.start_button.config(text='Stop',command=self.stop_remote_script_and_detection)
        threading.Thread(target=self.start_remote_script_and_detection, daemon=True).start()
    def start_remote_script_and_detection(self):
        self.scr_n_dtct_event.set()
        try:
            threading.Thread(target=self.send_with_bt, daemon=True).start()
        finally:
            self.script_run.wait()
            self.after(0, self.launch_detection_process)
    def stop_remote_script_and_detection(self):
        self.scr_n_dtct_event.clear()
        self.progress.stop()
        self.start_button.configure(text='Restart',command=self.on_start_button_click)
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect('raspberrypi.local', username='admin', password=self.controller.password)
            client.exec_command('pkill -f temp_script.sh')
        except Error:
            print(Error)

    def send_with_bt(self):
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect('raspberrypi.local', username='admin', password=self.controller.password)
            stdin, stdout, stderr = client.exec_command('cat script.sh')
            output = stdout.read().decode()
            output = output.replace('put_mac_here', self.controller.selected_mac)
            output = output.replace('put_obex_here', self.controller.obex_channel)
            output_escaped = output.replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')
            remote_write_command = f'echo "{output_escaped}" > temp_script.sh && chmod +x temp_script.sh'
            client.exec_command(remote_write_command)
            stdin,stdout,stderr=client.exec_command('cat temp_script.sh')
            print(stdout.read().decode())
            temp_script_path=r'/home/admin/temp_script.sh'
            command = f"nohup bash {temp_script_path} > /home/admin/script.log 2>&1 &"
            stdin,stdout,stderr=client.exec_command(command)
            stdout.channel.recv_exit_status()
            self.script_run.set()
        except Exception as e:
            self.after(0, lambda: self.status_label.config(text=f"Error: {e}"))
            self.progress.stop()
        finally:
            client.exec_command('exit')
            client.close()
    def send_images_to_pi(self):
           ssh = paramiko.SSHClient()
           ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
           ssh.connect(hostname='raspberrypi.local', username='admin', password=self.controller.password)
           sftp = ssh.open_sftp()
           while self.scr_n_dtct_event.is_set():
                images=self.controller.dt_and_s.get_imgs_to_send()
                if not images.empty():
                        conf_path,conf_name=images.get()
                        sftp.put(conf_path, f'/home/admin/Pictures/{conf_name}')
                        self.controller.dt_and_s.pop_one()
                        time.sleep(5)
                        stdin,stdout,stderr=ssh.exec_command('cat alertscript.sh')
                        output=stdout.read().decode().replace('macaddress',self.controller.selected_mac).replace('obexchannel',self.controller.obex_channel).replace('DATETIME',datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                        output_escaped = output.replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')
                        remote_write_command = f'echo "{output_escaped}" > temp_alert.sh && chmod +x temp_alert.sh'
                        stdin, stdout, stderr=ssh.exec_command(remote_write_command)
                        stdout.channel.recv_exit_status()
                        stdin, stdout, stderr=ssh.exec_command('./temp_alert.sh')
                        stdout.channel.recv_exit_status()
                        time.sleep(3)
           sftp.close()
           ssh.close()
    def launch_detection_process(self):
        self.status_label.config(text="Running object detection...")
        self.progress.stop() 
        try:
            obj_thread=threading.Thread(target=self.controller.dt_and_s.object_detection,args=(self.controller.folder_path,self.scr_n_dtct_event),daemon=True)
            snd_thread=threading.Thread(target=self.send_images_to_pi ,daemon=True)
            obj_thread.start()
            snd_thread.start()
        except Error:
            print(Error)
if __name__ == "__main__":
    app = App()
    app.mainloop()

