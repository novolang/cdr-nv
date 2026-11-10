# Every shape a field can take, with defaults and constants.  The fixture
# for the tests of the generator: not a ROS message.

int32 LIMIT=100
float64 PI = 3.14159
string GREETING="hi # there"
bool FLAG=true
uint8 MASK=0xff
int8 LOW=-128

# Fixed arrays.
uint8[4] fixed_bytes
float32[2] fixed_floats
string[2] fixed_strings
Inner[2] fixed_nested

# Bounded sequences.
int32[<=3] bounded_ints
string<=5[<=2] bounded_strings
Inner[<=2] bounded_nested
int16[<=1] single

# Unbounded sequences.
int16[] open_ints
string[] open_strings
Inner[] open_nested

Inner one
cdr_test_msgs/Inner two

# Defaults.
int32 count 7
string label 'a"b$c\d'
string<=3 tag "x"
float64 gain 1.5
bool enabled True
int8[3] trio [1, -2, 3]
uint16[] seeds [10, 20]
float32 ratio 0.25
uint64 big 9
float32 neg -0.5
float64 tiny 1e3
float64[] none_yet []
string type
