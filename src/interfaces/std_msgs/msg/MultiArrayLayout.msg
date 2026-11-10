# The multiarray declares a generic multi-dimensional array of a
# particular data type.  Dimensions are ordered from outer to inner.
# That is, the dimension at index 0 has the largest stride.

MultiArrayDimension[] dim # Array of dimension properties
uint32 data_offset        # padding bytes at front of data
