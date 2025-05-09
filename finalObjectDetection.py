import cv2
import os
from cv2_enumerate_cameras import enumerate_cameras
import torch
import tensorrt as trt
import pycuda.driver as cuda
import numpy as np
import cv2
import torchvision.transforms as T
from datetime import datetime
import multiprocessing
import threading
from queue import Queue


TRT_LOGGER = trt.Logger(trt.Logger.WARNING)
with open("model_dynamic_batch.trt", "rb") as f:
    engine_data = f.read()
gpu_lock = multiprocessing.Semaphore(1)
def postprocess(output, conf_threshold=0.5, iou_threshold=0.5):
    # Assuming the model output is in the format [batch, num_boxes, 6] (x1, y1, x2, y2, class_id, score)
    boxes = []
    confidences = []
    class_ids = []

    for i in range(len(output)):
        pred = output[i]
        pred = pred.reshape(-1, 6)
        pred = pred[pred[:, 4] > conf_threshold]

        if pred.shape[0] == 0:
            continue

        # Extract boxes, class IDs, and confidences
        x1, y1, x2, y2, score, class_id = pred.T
        boxes.append(np.array([x1, y1, x2, y2]).T)
        confidences.append(score)
        class_ids.append(class_id)

    if not boxes or not confidences or not class_ids:
        return [], [], [], []

    print('here')
    boxes = np.concatenate(boxes, axis=0)
    confidences = np.concatenate(confidences, axis=0)
    class_ids = np.concatenate(class_ids, axis=0)

    indices = cv2.dnn.NMSBoxes(boxes.tolist(), confidences.tolist(), conf_threshold, iou_threshold)
    return indices, boxes, confidences, class_ids

def cam_work(idx,output_dir):
    with gpu_lock:
        batch=[]
        cap=cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            print(f'ERROR:Could not open camera {cam_idxs[0]}')
        while True:
            ret,frame=cap.read()
            if not ret:
                break
            batch.append(frame)
            if len(batch)==8:
                batch_np=pre_process(batch)
                res=process(batch_np)
                indices, boxes, confidences, class_ids=postprocess(res[0])
                img_create(indices,boxes,batch,output_dir)
                batch.clear()
            cv2.imshow(f'Camera{idx}',frame)
        cap.release()


def pre_process(batch):
    transform = T.Compose([
        T.ToPILImage(),                  # Convert NumPy array to PIL image
        T.Resize((640, 640)),            # Resize to model's expected input
        T.ToTensor(),                    # Converts to tensor and scales to [0, 1]
        T.Normalize(mean=[0.0, 0.0, 0.0], std=[1.0, 1.0, 1.0])  # Optional: adjust if needed
    ])
    tensor_batch = torch.stack([transform(frame) for frame in batch])
    batch_np = tensor_batch.cpu().numpy().astype(np.float32)
    return batch_np

def get_cam_idx():
    indexList=[]
    for camera_info in enumerate_cameras(cv2.CAP_MSMF):
        if(camera_info.name=='Brio 300'):
            indexList.append(camera_info.index)
    return indexList
def process(batch_np):
    runtime = trt.Runtime(TRT_LOGGER)
    logger = trt.Logger(trt.Logger.VERBOSE)
    builder = trt.Builder(logger)
    engine = runtime.deserialize_cuda_engine(engine_data)
    context = engine.create_execution_context()
    input_shape = (8, 3, 640, 640)
    output_shape = (8,5,8400)
    context.set_input_shape('images',input_shape)
    input_size = np.prod(input_shape) * np.dtype(np.float32).itemsize
    output_size = np.prod(output_shape) * np.dtype(np.float32).itemsize
    cuda.init()
    dev = cuda.Device(0)
    ctx = dev.make_context()
    input_device = cuda.mem_alloc(int(input_size))
    output_device = cuda.mem_alloc(int(output_size))
    h_input = np.empty(input_shape, dtype=np.float32)
    h_output = np.empty(output_shape, dtype=np.float32)
    try:
        cuda.memcpy_htod(input_device, batch_np)
        context.execute_v2([int(input_device), int(output_device)])
        cuda.memcpy_dtoh(h_output, output_device)
        num_detections = (h_output.size // 8) // 6
        h_output = h_output.reshape(8, num_detections, 6)
        return h_output
    finally:
        ctx.detach()
def img_create(indices_cam,boxes_cam,batch,output_dir):
    counter=1
    for i,j in zip(np.array(indices_cam).flatten(),batch):
        x1, y1, x2, y2 = boxes_cam[i]
        cv2.rectangle(j, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
        label = f"Person"
        cv2.putText(j, label, (int(x1), int(y1)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        before=datetime.now().strftime('%Y-%m-%d.%H:%M:%S')
        img_name=output_dir+'\\'+datetime.now().strftime('%Y_%m_%d.%H_%M_%S')
        if(os.path.isfile(img_name)):
            img_name= img_name+str(counter)
            counter+=1
        cv2.imwrite(img_name+'.jpg',j)
        after=datetime.now().strftime('%Y-%m-%d.%H:%M:%S')
        if(after!=before):
            counter=1

if __name__ == "__main__":
    cam_idxs=get_cam_idx()
    output_dir = r"C:\Users\omkad\source\repos\finalObjectDetection\finalObjectDetection\images"
    os.makedirs(output_dir, exist_ok=True)
    process1 = multiprocessing.Process(target=cam_work,args=(cam_idxs[0],output_dir))
    process2 = multiprocessing.Process(target=cam_work,args=(cam_idxs[1],output_dir))
    try:
        process1.start()
        process2.start()
        process1.join()
        process2.join()
    except KeyboardInterrupt:

        print("Terminating processes...")
        process1.terminate()
        process2.terminate()
        process1.join()
        process2.join()
    cv2.destroyAllWindows()
