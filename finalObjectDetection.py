from ultralytics import YOLO
import cv2
import os
import time
from cv2_enumerate_cameras import enumerate_cameras
import torch
import tensorrt as trt
import pycuda.driver as cuda
import pycuda.autoinit
import numpy as np
import cv2
import torchvision.transforms as T


TRT_LOGGER = trt.Logger(trt.Logger.WARNING)
with open("your_model.engine", "rb") as f, trt.Runtime(TRT_LOGGER) as runtime:
    engine = runtime.deserialize_cuda_engine(f.read())
def postprocess(output, conf_threshold=0.5, iou_threshold=0.4):
    # Assuming the model output is in the format [batch, num_boxes, 6] (x1, y1, x2, y2, class_id, score)
    boxes = []
    confidences = []
    class_ids = []

    for i in range(len(output)):
        pred = output[i]
        # Filter predictions with score > confidence threshold
        pred = pred[pred[:, 4] > conf_threshold]
        
        if pred.shape[0] == 0:
            continue

        # Extract boxes, class IDs, and confidences
        x1, y1, x2, y2, score, class_id = pred.T
        boxes.append(np.array([x1, y1, x2, y2]).T)
        confidences.append(score)
        class_ids.append(class_id)

    # Apply NMS (Non-Maximum Suppression)
    boxes = np.concatenate(boxes, axis=0)
    confidences = np.concatenate(confidences, axis=0)
    class_ids = np.concatenate(class_ids, axis=0)

    indices = cv2.dnn.NMSBoxes(boxes.tolist(), confidences.tolist(), conf_threshold, iou_threshold)
    return indices, boxes, confidences, class_ids

# Create an execution context
# Check all bindings

# Get the number of input/output tensors (bindings)
num_io_tensors = engine.num_io_tensors
print(f"Number of I/O tensors (bindings): {num_io_tensors}")



#inspector = engine.create_engine_inspector()

#for i in range(inspector.num_bindings):
#    binding_type = inspector.binding_type(i)
#    tensor_name = inspector.get_binding_name(i)
#    print(f"Binding {i} - Name: {tensor_name}, Type: {binding_type}")




context = engine.create_execution_context()

# Allocate buffers
input_shape = (8, 3, 640, 480)  # Example shape; adapt to your model
input_size = np.prod(input_shape)
output_size = 960  # Change based on your model output

# Allocate host and device buffers
input_array = np.random.random(input_size).astype(np.float32)
output_array = np.empty(output_size, dtype=np.float32)
input_device = cuda.mem_alloc(input_array.nbytes)
output_device = cuda.mem_alloc(output_array.nbytes)

indexList=[]
for camera_info in enumerate_cameras(cv2.CAP_MSMF):
    if(camera_info.name=='Brio 300'):
        indexList.append(camera_info.index)
output_dir = r"./images"
os.makedirs(output_dir, exist_ok=True)

# Counter for saved images
image_count = [1, 1]  # Separate counters for each camera
count=0
cap1 = cv2.VideoCapture(indexList[0])
cap2 = cv2.VideoCapture(indexList[1])  # Camera 1

# Check if cameras opened successfully
if not cap1.isOpened() or not cap2.isOpened():
    print("Error: Could not open one or both cameras.")
    exit()
batch1=[]
batch2=[]
batchsize=8
while True:
    # Start timer for frame processings
    start_time = time.time()

    # Read frames from both cameras
    ret1, frame1 = cap1.read()
    ret2, frame2 = cap2.read()

    if not ret1 or not ret2:
        break
    batch1.append(frame1)
    batch2.append(frame2)
    results1=None
    results2=None
    frames1=[]
    frames2=[]
    transform = T.Compose([
    T.ToPILImage(),                  # Convert NumPy array to PIL image
    T.Resize((640, 480)),            # Resize to model's expected input
    T.ToTensor(),                    # Converts to tensor and scales to [0, 1]
    T.Normalize(mean=[0.0, 0.0, 0.0], std=[1.0, 1.0, 1.0])  # Optional: adjust if needed
])
    if len(batch1)==batchsize and len(batch2)==batchsize:
        
        tensor_batch1 = torch.stack([transform(frame) for frame in batch1])
        tensor_batch2 = torch.stack([transform(frame) for frame in batch2])

        # Move to GPU
        tensor_batch1 = tensor_batch1.cuda()
        tensor_batch2 = tensor_batch2.cuda()

        # Convert to NumPy for TensorRT
        batch_np1 = tensor_batch1.cpu().numpy()
        batch_np2 = tensor_batch2.cpu().numpy()

        # Copy batches to device memory
        cuda.memcpy_htod(input_device, batch_np1)
        cuda.memcpy_htod(input_device, batch_np2)

        # Perform inference with TensorRT
        context.execute_v2([int(input_device), int(output_device)])

        # Copy output from device to host
        cuda.memcpy_dtoh(output_array, output_device)
        num_detections = (output_array.size // 8) // 6
        print("Output shape before postprocess:", output_array.shape)
        print("Sample output[0]:", output_array[0])

        output_array = output_array.reshape(batchsize, num_detections, 6)
        indices_cam1, boxes_cam1, confidences_cam1, class_ids_cam1 = postprocess(output_array[:8])
        indices_cam2, boxes_cam2, confidences_cam2, class_ids_cam2 = postprocess(output_array[8:])

        # Draw bounding boxes and labels on the frames (Camera 1)
        for i in indices_cam1.flatten():
            x1, y1, x2, y2 = boxes_cam1[i]
            cv2.rectangle(frame1, (x1, y1), (x2, y2), (0, 255, 0), 2)  # Green box
            label = f"Class: {int(class_ids_cam1[i])}, Score: {confidences_cam1[i]:.2f}"
            cv2.putText(frame1, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

        # Draw bounding boxes and labels on the frames (Camera 2)
        for i in indices_cam2.flatten():
            x1, y1, x2, y2 = boxes_cam2[i]
            cv2.rectangle(frame2, (x1, y1), (x2, y2), (0, 255, 0), 2)  # Green box
            label = f"Class: {int(class_ids_cam2[i])}, Score: {confidences_cam2[i]:.2f}"
            cv2.putText(frame2, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

        # Reset frame counters and GPU frame lists for the next batch

        frames1.clear()
        frames2.clear()

    # Calculate elapsed time for the frame (in milliseconds)
    end_time = time.time()
    process_time_ms = (end_time - start_time) * 1000  # Convert to milliseconds

    # Output the processing time for the current frame
    print(f"Processing Time for Current Batch: {process_time_ms:.2f} ms")
    # Show frames for both cameras
    cv2.imshow("Camera 0", frame1)
    cv2.imshow("Camera 1", frame2)

    # Exit on pressing 'q'
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release the cameras and close all windows
cap1.release()
cap2.release()
cv2.destroyAllWindows()
