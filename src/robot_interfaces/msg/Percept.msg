# A single perception result produced by robot_perception.
std_msgs/Header header          # stamp + frame_id (e.g. camera or base_link)
string label                    # e.g. "apriltag:3", "color:red", "person"
float32 confidence              # 0.0 - 1.0
geometry_msgs/Point position    # target position in header.frame_id (metres)
float32 bearing                 # bearing to target (rad), + = left

# Image-plane bounding box, normalised [0,1] against the source frame so a viewer
# can overlay it at any display size without knowing the camera resolution. All
# zero = no box (e.g. a LiDAR percept, which has no image footprint).
float32 bbox_x                  # left edge
float32 bbox_y                  # top edge
float32 bbox_w                  # width
float32 bbox_h                  # height
