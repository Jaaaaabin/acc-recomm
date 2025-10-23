#! python3
#


def cross_product(v1, v2):
    """
    Compute the cross product of two 3D vectors.
    To find perpendicular vectors and determine if lines are parallel.
    """
    return (
        v1[1] * v2[2] - v1[2] * v2[1],
        v1[2] * v2[0] - v1[0] * v2[2],
        v1[0] * v2[1] - v1[1] * v2[0]
    )

def dot_product(v1, v2):
    """
    Compute the dot product of two 3D vectors.
    For projection of vectors and for checking relative positions along the direction vectors.
    """
    return v1[0] * v2[0] + v1[1] * v2[1] + v1[2] * v2[2]

def subtract_vectors(v1, v2):
    """
    Subtract two vectors (v1 - v2).
    To calculate direction vectors and differences between points.
    """
    return (v1[0] - v2[0], v1[1] - v2[1], v1[2] - v2[2])

def is_close(p1, p2, tol=1e-5):
    """
    Check if two 3D points are within a given tolerance.
    To ensure that intersection points are close enough within a small tolerance to account for floating-point precision.
    """
    return all(abs(a - b) < tol for a, b in zip(p1, p2))

def are_3d_lines_real_intersecting(line_p, line_q, tol=1e-5):
    """
    Check if two 3D line segments intersect.
    Line 1: (p0 -> p1)
    Line 2: (q0 -> q1)
    
    Returns True if the lines intersect, otherwise False.
    """
    p0, p1 = line_p
    q0, q1 = line_q

    # Line 1 direction vector (p0 -> p1)
    p_dir = subtract_vectors(p1, p0)
    
    # Line 2 direction vector (q0 -> q1)
    q_dir = subtract_vectors(q1, q0)
    
    # Vector from p0 to q0
    r = subtract_vectors(q0, p0)
    
    # Cross product of direction vectors (to determine if lines are parallel)
    cross_dir = cross_product(p_dir, q_dir)
    
    # If cross product is zero, lines are either parallel or collinear
    if cross_dir == (0, 0, 0):
        # Check if the lines are collinear by testing if vector r is also parallel
        if cross_product(p_dir, r) == (0, 0, 0):
            # Check if the segments overlap by projecting points onto the line
            p_dir_dot = dot_product(p_dir, p_dir)
            t0 = dot_product(subtract_vectors(q0, p0), p_dir) / p_dir_dot
            t1 = dot_product(subtract_vectors(q1, p0), p_dir) / p_dir_dot
            
            # The segments overlap if the projections lie within the segment [0, 1]
            return (0 <= t0 <= 1) or (0 <= t1 <= 1)
        else:
            # Parallel but not collinear
            return False
    else:
        # Lines are not parallel, so we check for intersection
        cross_pq = cross_product(r, q_dir)
        cross_qp = cross_product(r, p_dir)
        
        # Solve parametric t values
        denom = dot_product(cross_dir, cross_dir)
        
        # If the denominator is zero, the lines are skew and will not intersect
        if denom == 0:
            return False
        
        # Solve t0 and t1 for intersection point on both lines
        t0 = dot_product(cross_pq, cross_dir) / denom
        t1 = dot_product(cross_qp, cross_dir) / denom
        
        # The segments intersect if both t values are between 0 and 1
        # AND the intersection point is within the bounds of the segments
        if (0 <= t0 <= 1) and (0 <= t1 <= 1):
            # This step ensures the intersection is within the 3D space of the segments
            intersection_point_p = (p0[0] + t0 * p_dir[0], p0[1] + t0 * p_dir[1], p0[2] + t0 * p_dir[2])
            intersection_point_q = (q0[0] + t1 * q_dir[0], q0[1] + t1 * q_dir[1], q0[2] + t1 * q_dir[2])

            # Return True if the intersection points are close within tolerance
            return is_close(intersection_point_p, intersection_point_q, tol)
        
        return False

def shifted_parallel_lines(p0, p1, d=0.0):
    """
    d should be the "half width of the wall itself".
    """
    d = d*0.5

    # Calculate the direction vector of the line (p1 - p0)
    direction = (p1[0] - p0[0], p1[1] - p0[1])
    
    # Normalize the direction vector
    length = (direction[0]**2 + direction[1]**2) ** 0.5
    unit_direction = (direction[0] / length, direction[1] / length)
    
    # Calculate the normal vector in the XY plane
    normal = (-unit_direction[1], unit_direction[0])  # Perpendicular to the direction vector
    
    # Shift points left and right along the normal vector
    p0_left = [p0[0] + normal[0] * d, p0[1] + normal[1] * d, p0[2]]
    p1_left = [p1[0] + normal[0] * d, p1[1] + normal[1] * d, p1[2]]
    
    p0_right = [p0[0] - normal[0] * d, p0[1] - normal[1] * d, p0[2]]
    p1_right = [p1[0] - normal[0] * d, p1[1] - normal[1] * d, p1[2]]
    
    return [[p0_left, p1_left],[p0_right, p1_right]]

def extended_line(p0, p1, e=0.0):
    """
    d should be the "half width of the targeted connected wall".
    """
    e = e*0.5

    # Calculate the direction vector from p0 to p1
    direction = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    
    # Calculate the length of the original line
    line_length = (direction[0]**2 + direction[1]**2 + direction[2]**2) ** 0.5
    
    # Normalize the direction vector
    unit_direction = (direction[0] / line_length, direction[1] / line_length, direction[2] / line_length)
    
    # Extend p0 backwards and p1 forwards by the extension length: half width.
    new_p0 = [p0[0] - unit_direction[0] * e,
              p0[1] - unit_direction[1] * e,
              p0[2] - unit_direction[2] * e]
    
    new_p1 = [p1[0] + unit_direction[0] * e,
              p1[1] + unit_direction[1] * e,
              p1[2] + unit_direction[2] * e]
    
    return [new_p0, new_p1]

def are_lines_intersecting_by_shifting_extending(
    info_line_p, info_line_q, set_shift=True, set_shift_extend=True, tol=1e-5):
    """
    wall_p:
        endpoints: p0, p1
        width: d_p
    wall_q:
        endpoints: q0, q1
        width: d_q
    """

    [p0, p1, d_p] = info_line_p
    [q0, q1, d_q] = info_line_q
    
    # shifted lines.
    [line_p_shift_left, line_p_shift_right] = shifted_parallel_lines(p0, p1, d_p)
    [line_q_shift_left, line_q_shift_right] = shifted_parallel_lines(q0, q1, d_q)
    
    if set_shift and not set_shift_extend:
    
        return any([
            are_3d_lines_real_intersecting(line_p_shift_left, line_q_shift_left, tol),
            are_3d_lines_real_intersecting(line_p_shift_left, line_q_shift_right, tol),
            are_3d_lines_real_intersecting(line_p_shift_right, line_q_shift_left, tol),
            are_3d_lines_real_intersecting(line_p_shift_right, line_q_shift_right, tol)
        ])
    
    elif set_shift_extend:

        # extended shifted lines.
        extend_line_p_shift_left = extended_line(line_p_shift_left[0], line_p_shift_left[1], d_q)
        extend_line_p_shift_right = extended_line(line_p_shift_right[0], line_p_shift_right[1], d_q)
        extend_line_q_shift_left = extended_line(line_q_shift_left[0], line_q_shift_left[1], d_p)
        extend_line_q_shift_right = extended_line(line_q_shift_right[0], line_q_shift_right[1], d_p)
    
        return any([
            are_3d_lines_real_intersecting(extend_line_p_shift_left, extend_line_q_shift_left, tol),
            are_3d_lines_real_intersecting(extend_line_p_shift_left, extend_line_q_shift_right, tol),
            are_3d_lines_real_intersecting(extend_line_p_shift_right, extend_line_q_shift_left, tol),
            are_3d_lines_real_intersecting(extend_line_p_shift_right, extend_line_q_shift_right, tol),
        ])
    
    else:
        print ("please set at least one of the conditions (set_shift, set_shift_extend) as TRUE.")
        return None
    
def calculate_bbx_overlap_volume_by_minmax_xyz(min1, max1, min2, max2):
    x_overlap = max(0, min(max1[0], max2[0]) - max(min1[0], min2[0]))
    y_overlap = max(0, min(max1[1], max2[1]) - max(min1[1], min2[1]))
    z_overlap = max(0, min(max1[2], max2[2]) - max(min1[2], min2[2]))
    return x_overlap * y_overlap * z_overlap

def get_XYZpoint_as_list(p):
    return [p.X, p.Y, p.Z]

def vector_length(v):
    vector_length_squared = dot_product(v, v)
    return vector_length_squared ** 0.5

def are_lines_parallel_with_distance(line_a_points, line_b_points, tol=1e-5):
    """
    Checks if two lines are parallel. If so, returns (True, distance).
    Otherwise, returns (False, None).
    Each line is a flat list of 6 coordinates: [x1, y1, z1, x2, y2, z2]
    """

    p0, p1 = line_a_points
    q0, q1 = line_b_points
    v1 = subtract_vectors(p1, p0)
    v2 = subtract_vectors(q1, q0)

    cross = cross_product(v1, v2)
    cross_norm = vector_length(cross)

    if cross_norm > tol:
        return False, None  # Not parallel

    diff = subtract_vectors(q0, p0)
    v1_length = vector_length(v1)
    if v1_length < tol:
        return False, None  # degenerate

    unit_v1 = tuple(a / v1_length for a in v1)
    proj_len = dot_product(diff, unit_v1)
    proj_vec = tuple(proj_len * a for a in unit_v1)

    orthogonal = subtract_vectors(diff, proj_vec)
    distance = vector_length(orthogonal)

    return True, distance

def is_point_near_line(line_location, point_location, tol=1e-5, tol_segment=0.05):
    """
    Checks if a point is near an infinite line defined by a LocationCurve.
    
    :param line_location: LocationCurve (e.g., from wall.Location)
    :param point_location: The XYZ point (e.g., column.Location)
    :param max_distance: The threshold distance to consider "near"
    :return: (True, distance) if near; (False, distance) if not
    """
    line_location_p0, line_location_p1 = line_location
    
    v = subtract_vectors(point_location, line_location_p0)             # vector from line_location_p0 (on the line) to q (the point).
    line_dir = subtract_vectors(line_location_p1, line_location_p0)     # direction vector of the line
    line_len = vector_length(line_dir)      # computes the length of the line direction vector
    if line_len < tol:                      # if close to 0, we consider the line invalid.
        return None  # Degenerate line

    unit_dir = [x / line_len for x in line_dir]     # normalizes the direction vector
    proj_len = dot_product(v, unit_dir)             # scalar projection of vector v onto the direction of the line.
    
    # Check where the projection lands
    t = proj_len / line_len
    is_within_segment = (0.0-tol_segment) <= t <= (1.0+tol_segment)
    
    proj = [proj_len * x for x in unit_dir]         # convert the scalar back into a vector: the actual projection vector.
    orthogonal = subtract_vectors(v, proj)          # the difference between v and its projection is the perpendicular vector from the point to the line
    distance_point2line = vector_length(orthogonal)            # take the length of that perpendicular vector, this is the distance from the point to the line.

    return is_within_segment, distance_point2line

def are_points_aligned(point_list, tol=1e-5):
    """
    Checks if all points in the list lie on the same straight line (3D collinearity).
    
    :param point_list: list of points (each is a list or tuple of 3 floats)
    :return: True if all points lie on a straight line, else False
    """
    if len(point_list) < 2:
        return True  # Trivially aligned

    p0 = point_list[0]
    p1 = point_list[1]
    ref_dir = subtract_vectors(p1, p0)
    ref_len = vector_length(ref_dir)

    if ref_len < tol:
        return False  # First two points too close to define a line

    for i in range(2, len(point_list)):
        pi = point_list[i]
        vi = subtract_vectors(pi, p0)
        cross = cross_product(ref_dir, vi)
        if vector_length(cross) > tol:
            return False  # Not collinear

    return True

def get_combinations(input_list, N):
    """
    Returns all combinations of length N from input_list.
    Does not use any external libraries.
    """
    if N == 0:
        return [[]]
    if int(N) != N:
        print ("Size of combination should be integer.+")
    if len(input_list) < N:
        return []
    
    result = []
    for i in range(len(input_list)):
        first = input_list[i]
        rest = input_list[i+1:]
        for subcombo in get_combinations(rest, N - 1):
            result.append([first] + subcombo)
    
    return result