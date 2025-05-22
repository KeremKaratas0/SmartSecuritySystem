import multiprocessing
import sys
import time
from ultralytics import YOLO
import cv2
import os
import datetime
import paramiko
from cv2_enumerate_cameras import enumerate_cameras
import threading


def cam_work(idx,in_queue):
    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) 
    if not cap.isOpened():
        exit()
    batch=[]
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        cv2.imshow(f'Camera {idx}',frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        batch.append(frame)
        if(len(batch)==8):
                in_queue.put(batch.copy(), block=False)
                batch.clear()
    cap.release()
    cv2.destroyAllWindows()
class object_detect_and_send():
    def __init__(self):
        self.imgs_to_send=multiprocessing.Queue()
    def get_cam_idx(self):
        self.indexList=[]
        for camera_info in enumerate_cameras(cv2.CAP_DSHOW):
            if(camera_info.name=='Brio 300'):
               self. indexList.append(camera_info.index) 
        self.waiter.set()

    def save_img(self,results, batch, output_dir):
        cur_time=datetime.datetime.now()
        cur_time= cur_time.strftime("%Y_%m_%d.%H_%M_%S")
        count=0
        frames_with_conf=dict()
        for result, frame in zip(results, batch):
            has_person = False
            for box in result.boxes:
                cls_id = int(box.cls[0])
                class_name = result.names[cls_id]
                if class_name.lower() == "person":
                    has_person = True
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, "Person", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            if has_person:
                filename = f"{cur_time}({count}).jpg"
                filepath = os.path.join(output_dir, filename)
                cv2.imwrite(filepath, frame)
                count+=1 
                if result.boxes and len(result.boxes) > 0:
                    frames_with_conf[float(result.boxes.conf.max().item())]=(filepath,filename)
        if(frames_with_conf):
            max_conf=max(frames_with_conf.keys())
            self.imgs_to_send.put(frames_with_conf[max_conf])  
    def get_imgs_to_send(self):
        return self.imgs_to_send
    def pop_one(self):
        self.imgs_to_send.get()
    def object_detection(self,output_dir,event):
        model = YOLO(r"model.pt")  
        model.to('cuda')
        os.makedirs(output_dir, exist_ok=True)
        input_queue1=multiprocessing.Queue()
        input_queue2=multiprocessing.Queue()
        self.waiter=threading.Event()
        self.get_cam_idx()
        self.waiter.wait()
        process1=multiprocessing.Process(target=cam_work,args=(self.indexList[0],input_queue1))
        process2=multiprocessing.Process(target=cam_work,args=(self.indexList[1],input_queue2))
        process1.start()
        process2.start()
        try:
            while event.is_set():
                    batch1=input_queue1.get()
                    if len(batch1)!=0:
                        results1 = model(batch1, verbose=False)
                        self.save_img(results=results1, batch=batch1,output_dir=output_dir)
                    batch2=input_queue2.get()           
                    if len(batch2)!=0:
                        results2 = model(batch2, verbose=False)
                        self.save_img(results=results2, batch=batch2,output_dir=output_dir)
        finally:
            process1.join()
            process2.join()
            process1.terminate()
            process2.terminate()






