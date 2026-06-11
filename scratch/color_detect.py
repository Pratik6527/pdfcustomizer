import cv2
import numpy as np

def test_watermark_color(img_path):
    img = cv2.imread(img_path)
    if img is None:
        print("Could not load image")
        return
        
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Background mask: V > 240, S < 20 (White/Light Gray)
    bg_mask = cv2.inRange(hsv, np.array([0, 0, 240]), np.array([180, 20, 255]))
    
    # Foreground mask: V < 130 (Dark text)
    fg_mask = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([180, 255, 130]))
    
    # We want pixels that are NEITHER background nor dark foreground
    combined_bg_fg = cv2.bitwise_or(bg_mask, fg_mask)
    target_pixels_mask = cv2.bitwise_not(combined_bg_fg)
    
    # Extract the target pixels
    target_hsv = hsv[target_pixels_mask == 255]
    
    if len(target_hsv) == 0:
        print("No mid-tone pixels found")
        return
        
    print(f"Found {len(target_hsv)} potential watermark pixels.")
    
    # We can find the median color of these pixels
    median_h = np.median(target_hsv[:, 0])
    median_s = np.median(target_hsv[:, 1])
    median_v = np.median(target_hsv[:, 2])
    
    print(f"Median HSV: ({median_h}, {median_s}, {median_v})")
    
    # Create a mask around this median color
    tolerance_h = 20
    tolerance_s = 50
    tolerance_v = 50
    
    lower_bound = np.array([
        max(0, median_h - tolerance_h),
        max(0, median_s - tolerance_s),
        max(0, median_v - tolerance_v)
    ])
    
    upper_bound = np.array([
        min(180, median_h + tolerance_h),
        min(255, median_s + tolerance_s),
        min(255, median_v + tolerance_v)
    ])
    
    # Now we mask the original image using this color bound
    color_mask = cv2.inRange(hsv, lower_bound, upper_bound)
    
    print("Color mask created with bounds:")
    print("Lower:", lower_bound)
    print("Upper:", upper_bound)
    
    return color_mask

print("Script created")
