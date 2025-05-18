import multiprocessing
from ultralytics import YOLO
import cv2
import os
import datetime
import paramiko
from cv2_enumerate_cameras import enumerate_cameras
from detect import gui


def get_cam_idx():
    indexList=[]
    for camera_info in enumerate_cameras(cv2.CAP_DSHOW):
        if(camera_info.name=='Brio 300'):
            indexList.append(camera_info.index)
    return indexList


def cam_work(idx,in_queue):
    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) 
    if not cap.isOpened():
        exit()
    batch=[]
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        batch.append(frame)
        if(len(batch)==8):
                in_queue.put(batch.copy(), block=False)
                batch.clear()
        cv2.imshow(f"Camera {idx}", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    cap.release()
    cv2.destroyAllWindows()


def save_img(sftp,results, batch, output_dir):
    cur_time=datetime.datetime.now()
    cur_time= cur_time.strftime("%Y_%m_%d.%H_%M_%S")
    count=0
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
            sftp.put(filepath, '/home/admin/Pictures/')
            count+=1 


def object_detection(output_dir,ip,pw):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=ip, username='admin', password=pw)
    sftp = ssh.open_sftp()
    model = YOLO(r"mert76.pt")  
    model.to('cuda')
    os.makedirs(output_dir, exist_ok=True)
    input_queue1=multiprocessing.Queue()
    input_queue2=multiprocessing.Queue()
    indexes=get_cam_idx()
    process1=multiprocessing.Process(target=cam_work,args=(indexes[0],input_queue1))
    process2=multiprocessing.Process(target=cam_work,args=(indexes[1],input_queue2))
    try:
        process1.start()
        process2.start()
        while True:
                batch1=input_queue1.get()
                if len(batch1)!=0:
                    results1 = model(batch1, verbose=False)
                    save_img(sftp=sftp,results=results1, batch=batch1,output_dir=output_dir)
                batch2=input_queue2.get()           
                if len(batch2)!=0:
                    results2 = model(batch2, verbose=False)
                    save_img(sftp=sftp,results=results2, batch=batch2,output_dir=output_dir)
    except KeyboardInterrupt:
        sftp.close()
        ssh.close()
        process1.terminate()
        process2.terminate()
        process1.join()
        process2.join()

if __name__=='__main__':
    object_detection(output_dir = r"")



