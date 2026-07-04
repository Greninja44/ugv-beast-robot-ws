# A single perception result produced by robot_perception.
std_msgs/Header header          # stamp + frame_id (e.g. camera or base_link)
string label                    # e.g. "apriltag:3", "color:red", "person"
float32 confidence              # 0.0 - 1.0
geometry_msgs/Point position    # target position in header.frame_id (metres)
float32 bearing                 # bearing to target (rad), + = left
