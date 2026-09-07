# Foundational Requirements
1. Create a libReflection.a, CMake based, that uses C++20, should be buildable on Linux and QNX (SDP 8.0). 
2. The core of the library is around the following interface class:
   ```
   class ClassHash {
        uint64_t words[4]; // 4 * 64 bits = 256 bits
    };

    class ClassReflection
    {
      public:
        using MemberList = std::vector<ClassReflection>;
        using EnumValues = std::unordered_map<std::string, std::int64_t>;
    
        /**
         * @brief Construct a new Class Reflection object
         */
        ClassReflection()
        : name(""),
          type(""),
          offset(0),
          size(0),
          count(1),
          members(),
          hash{0, 0, 0, 0},
          enum_name(""),
          enum_values(),
          bit_flag(false) {}

      public:
        std::string name;
        std::string type;
        std::uint32_t offset;
        std::uint32_t size;
        std::uint32_t count;
        MemberList members;
        ClassHash hash;
        std::string enum_name;
        EnumValues enum_values;
        bool bit_flag;
    };
	```
3. Add public member functions to access these members.
4. The goal of this implementation should match with or realize C++26 reflections but compilable on C++20 and usable on code without following the syntaxes or keywords that will be introduced in C++26.  This means this class must abstract the future C++26 methods and members, but has to be simple. In that respect modify (add or remove) member variables / functions or modify their types to get a minimal implementation working and usable.



# Folder structure
.
├── build/
├── CMakeLists.txt
├── README.md
├── release/
├── src/
└── version.txt
