; Java function and class definitions
; Extracts: class_declaration, interface_declaration, method_declaration, field_declaration

; Class declarations
(class_declaration
  name: (identifier) @name)

; Class declarations with superclass
(class_declaration
  name: (identifier) @name
  superclass: (type_identifier) @superclass)

; Class declarations with interfaces
(class_declaration
  name: (identifier) @name
  interfaces: (super_interfaces
    (type_list
      (type_identifier) @interface)))

; Interface declarations
(interface_declaration
  name: (identifier) @name)

; Interface declarations with extends
(interface_declaration
  name: (identifier) @name
  extends_interfaces: (interface_type_list) @extends)

; Enum declarations
(enum_declaration
  name: (identifier) @name)

; Method declarations
(method_declaration
  name: (identifier) @method_name
  parameters: (formal_parameters) @parameters)

; Method declarations with return type
(method_declaration
  type: (type_identifier) @return_type
  name: (identifier) @method_name)

; Constructor declarations
(method_declaration
  name: (identifier) @constructor_name
  parameters: (formal_parameters) @parameters)

; Void method declarations
(method_declaration
  type: (void_type) @void_return
  name: (identifier) @method_name)

; Abstract method declarations
(method_declaration
  "abstract" @abstract_keyword
  type: (type_identifier) @return_type
  name: (identifier) @method_name)

; Static method declarations
(method_declaration
  "static" @static_keyword
  type: (type_identifier) @return_type
  name: (identifier) @method_name)

; Field declarations
(field_declaration
  type: (type_identifier) @field_type
  declarators: (variable_declarator_list
    (variable_declarator
      name: (identifier) @field_name)))

; Static field declarations
(field_declaration
  "static" @static_keyword
  type: (type_identifier) @field_type)

; Final field declarations
(field_declaration
  "final" @final_keyword
  type: (type_identifier) @field_type)

; Annotated class declarations
(marker_annotation
  name: (identifier) @annotation)

; Generic class declarations
(class_declaration
  name: (identifier) @name
  type_parameters: (type_parameters) @generics)

; Generic method declarations
(method_declaration
  type_parameters: (type_parameters) @generics
  type: (type_identifier) @return_type
  name: (identifier) @method_name)

; Lambda expressions (for inline method definitions)
(lambda_expression
  parameters: (formal_parameters) @lambda_params)

; Inner class declarations
(class_declaration
  name: (identifier) @inner_class_name)
