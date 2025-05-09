import os
import shutil
import cv2

#Filtering code for datasets.

dataset_folder = r"..."
output_folder = r"..."
count = 0

os.makedirs(output_folder, exist_ok=True)

classes_file = os.path.join(dataset_folder, "classes.txt")
if os.path.exists(classes_file):
    shutil.copy(classes_file, os.path.join(output_folder, "classes.txt"))

def get_intersection_area(box1, box2):
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2

    x_left = max(x1, x2)
    y_top = max(y1, y2)
    x_right = min(x1 + w1, x2 + w2)
    y_bottom = min(y1 + h1, y2 + h2)

    if x_right < x_left or y_bottom < y_top:
        return 0

    return (x_right - x_left) * (y_bottom - y_top)

for file in os.listdir(dataset_folder):
    if file.endswith(".txt") and file != "classes.txt":
        txt_path = os.path.join(dataset_folder, file)
        jpg_path = os.path.join(dataset_folder, file.replace(".txt", ".jpg"))

        if not os.path.exists(jpg_path):
            print(f"{file}: Image not found, skipping.")
            continue

        img = cv2.imread(jpg_path)
        if img is None:
            print(f"{file}: Error loading image, skipping.")
            continue
        img_height, img_width, _ = img.shape
        img_area = img_width * img_height

        with open(txt_path, "r") as f:
            lines = f.readlines()

        bboxes = []
        person_area = 0

        for line in lines:
            parts = line.strip().split()
            if len(parts) < 5:
                continue

            class_id = int(parts[0])
            if class_id != 0:
                continue

            _, x_center, y_center, width, height = map(float, parts)
            bbox_width = width * img_width
            bbox_height = height * img_height
            bbox_x = (x_center * img_width) - (bbox_width / 2)
            bbox_y = (y_center * img_height) - (bbox_height / 2)

            bboxes.append((bbox_x, bbox_y, bbox_width, bbox_height))
            person_area += bbox_width * bbox_height

        for i in range(len(bboxes)):
            for j in range(i + 1, len(bboxes)):
                overlap_area = get_intersection_area(bboxes[i], bboxes[j])
                person_area -= overlap_area

        person_area = min(person_area, img_area)

        person_coverage = (person_area / img_area) * 100

        if 40 <= person_coverage:
            shutil.copy(txt_path, os.path.join(output_folder, file))
            shutil.copy(jpg_path, os.path.join(output_folder, file.replace(".txt", ".jpg")))
            print(f"{file}: GOOD ✅ (Person coverage: {person_coverage:.2f}%)")
            count += 1
        else:
            print(f"{file}: BAD ❌ (Person coverage: {person_coverage:.2f}%)")

print("Processing complete. Filtered dataset saved.")
print(count)
