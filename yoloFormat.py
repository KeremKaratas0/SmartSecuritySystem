import os
import cv2
from ultralytics import YOLO

#Code that prepares labels in YOLO format for datasets.

source_dir = "..."
output_dir = "..."

model = YOLO("yolov8n.pt")

os.makedirs(output_dir, exist_ok=True)

for filename in os.listdir(source_dir):
    if filename.lower().endswith(".png"):
        image_path = os.path.join(source_dir, filename)
        img = cv2.imread(image_path)
        h, w = img.shape[:2]

        results = model(image_path)[0]
        human_boxes = [box for box in results.boxes if int(box.cls) == 0]

        if not human_boxes:
            continue

        txt_filename = os.path.splitext(filename)[0] + ".txt"
        txt_path = os.path.join(output_dir, txt_filename)

        with open(txt_path, "w") as f:
            for box in human_boxes:
                x_center = (box.xywh[0][0] / w).item()
                y_center = (box.xywh[0][1] / h).item()
                width    = (box.xywh[0][2] / w).item()
                height   = (box.xywh[0][3] / h).item()
                f.write(f"0 {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n")

        cv2.imwrite(os.path.join(output_dir, filename), img)
