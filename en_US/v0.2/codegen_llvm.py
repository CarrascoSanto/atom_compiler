# -*- coding: utf-8 -*-

import llvmlite.ir as ir
import llvmlite.binding as llvm # llvm é o módulo binding
from typing import Dict, List, Optional, Union, Tuple, Set
import traceback # Para debug

import ast_nodes as ast

_global_string_counter = 0
_global_byte_array_counter = 0

def create_global_string_constant(module: ir.Module, value: str, name_prefix: str = ".str") -> ir.Value:
    global _global_string_counter
    unique_name = f"{name_prefix}.{_global_string_counter}"
    _global_string_counter += 1
    value_bytes = value.encode('utf8') + b'\x00'
    const_data = ir.Constant(ir.ArrayType(ir.IntType(8), len(value_bytes)), bytearray(value_bytes))
    global_var = ir.GlobalVariable(module, const_data.type, name=unique_name)
    global_var.linkage = "private"
    global_var.global_constant = True
    global_var.initializer = const_data
    global_var.unnamed_addr = True
    zero = ir.Constant(ir.IntType(32), 0)
    return global_var.gep([zero, zero])

def create_global_byte_array_constant(module: ir.Module, value_bytes: bytes, name_prefix: str = ".bstr") -> ir.GlobalVariable:
    global _global_byte_array_counter
    unique_name = f"{name_prefix}.{_global_byte_array_counter}"
    _global_byte_array_counter += 1
    byte_array_type = ir.ArrayType(ir.IntType(8), len(value_bytes))
    const_data = ir.Constant(byte_array_type, bytearray(value_bytes))
    global_var = ir.GlobalVariable(module, const_data.type, name=unique_name)
    global_var.linkage = "private"
    global_var.global_constant = True
    global_var.initializer = const_data
    global_var.unnamed_addr = True
    return global_var

class CodeGenVisitor:
    def __init__(self):
        llvm.initialize()
        llvm.initialize_all_targets()
        llvm.initialize_all_asmprinters()

        self.target = llvm.Target.from_default_triple()
        # Configurar a máquina de destino ANTES de tentar obter dados dela
        self.target_machine = self.target.create_target_machine() 
        
        # Obter data_layout e triple da máquina de destino
        try:
            # Tenta obter o objeto TargetData diretamente da TargetMachine
            target_data_obj = self.target_machine.target_data 
            data_layout_string = str(target_data_obj) # Converte para string para o módulo IR
            # print(f"DEBUG CodeGen Init: Data layout string obtido: {data_layout_string}")
        except Exception as e_tm_td:
             print(f"ERROR CodeGen Init: Falha ao obter TargetData da TargetMachine: {e_tm_td}")
             print("                     Usando fallback para data layout vazio.")
             target_data_obj = None # Marcar que não temos o objeto
             data_layout_string = "" # Fallback para string vazia

        self.module = ir.Module(name="atom_module")
        self.module.data_layout = data_layout_string
        self.module.triple = self.target.triple

        # --- Determinação do Tamanho do Ponteiro ---
        ptr_bit_width: int = 64 # Default fallback
        determined_int_ptr_type: ir.IntType = ir.IntType(ptr_bit_width)

        if target_data_obj: # Se conseguimos obter o objeto TargetData da TargetMachine
            try:
                # Tenta obter o tamanho em bits diretamente (método comum)
                ptr_bit_width = target_data_obj.get_pointer_size_in_bits() 
                determined_int_ptr_type = ir.IntType(ptr_bit_width)
                # print(f"DEBUG CodeGen Init: Pointer size (TargetMachine.target_data.get_pointer_size_in_bits()): {ptr_bit_width} bits.")
            except AttributeError:
                # Se get_pointer_size_in_bits não existir, tenta get_pointer_size() (sem arg)
                print(f"WARN CodeGen Init: Falha com get_pointer_size_in_bits(). Tentando get_pointer_size()...")
                try:
                    ptr_byte_size = target_data_obj.get_pointer_size() # Tenta sem argumento
                    ptr_bit_width = ptr_byte_size * 8
                    determined_int_ptr_type = ir.IntType(ptr_bit_width)
                    # print(f"DEBUG CodeGen Init: Pointer size (TargetMachine.target_data.get_pointer_size()): {ptr_byte_size} bytes ({ptr_bit_width} bits).")
                except Exception as e_get_ptr_size:
                    # Se ambos falharem, usa o fallback hardcoded
                    print(f"WARN CodeGen Init: Falha ao usar get_pointer_size() (erro: {e_get_ptr_size}). Usando fallback hardcoded para {ptr_bit_width} bits.")
                    determined_int_ptr_type = ir.IntType(ptr_bit_width) # Garante que está definido com o fallback
            except Exception as e_other_td:
                 # Outro erro inesperado com o objeto TargetData
                 print(f"WARN CodeGen Init: Erro inesperado ao usar TargetData ({type(target_data_obj).__name__}): {e_other_td}. Usando fallback hardcoded para {ptr_bit_width} bits.")
                 determined_int_ptr_type = ir.IntType(ptr_bit_width) # Garante que está definido com o fallback

        else: # Se não conseguimos o target_data_obj da TargetMachine
            print(f"ERROR CodeGen Init: Não foi possível obter TargetData da TargetMachine. Usando fallback hardcoded para {ptr_bit_width} bits para ponteiro.")
            determined_int_ptr_type = ir.IntType(ptr_bit_width) # Garante que está definido com o fallback
        
        print(f"INFO CodeGen Init: Tipo de ponteiro inteiro determinado como: {determined_int_ptr_type}")

        # Define self.llvm_types usando o tipo determinado
        self.llvm_types = {
            'i8': ir.IntType(8), 'u8': ir.IntType(8),
            'i16': ir.IntType(16), 'u16': ir.IntType(16),
            'i32': ir.IntType(32), 'u32': ir.IntType(32),
            'i64': ir.IntType(64), 'u64': ir.IntType(64),
            'bool': ir.IntType(1),
            'char': ir.IntType(8), # Assumindo char como u8
            'unit': ir.VoidType(),
            'int': ir.IntType(32),  # Default int/uint
            'uint': ir.IntType(32),
            'usize': determined_int_ptr_type, # <--- USA O TIPO DETERMINADO
            'isize': determined_int_ptr_type, # <--- USA O TIPO DETERMINADO
            # 'f32': ir.FloatType(), # Removido Float
            # 'f64': ir.DoubleType(), # Removido Float
        }
        
        # --- Pré-declara Funções de Runtime ---
        usize_type = self.llvm_types.get('usize') # Pega o tipo usize definido acima
        if usize_type and isinstance(usize_type, ir.IntType): # Verifica se é IntType
            try:
                # Declaração usando o usize_type determinado
                panic_func_ty = ir.FunctionType(ir.VoidType(), [usize_type, usize_type], var_arg=False)
                ir.Function(self.module, panic_func_ty, name="atom_panic_bounds_check")

                check_func_ty = ir.FunctionType(ir.VoidType(), [usize_type, usize_type], var_arg=False)
                ir.Function(self.module, check_func_ty, name="atom_do_bounds_check")
                # print("DEBUG CodeGen Init: Funções de runtime pré-declaradas.")
            except Exception as e_predecl:
                print(f"WARN CodeGen Init: Falha ao pré-declarar funções de runtime: {e_predecl}")
        else:
             print(f"WARN CodeGen Init: Tipo usize não determinado ou inválido ({usize_type}), não foi possível pré-declarar funções de runtime.")
        # --- Fim Pré-declaração ---

        # --- Inicializações dos outros membros ---
        self.builder: Optional[ir.IRBuilder] = None
        self.current_function_name: Optional[str] = None
        self.llvm_symbol_table: List[Dict[str, ir.Value]] = [{}]
        self.llvm_defined_structs: Dict[str, ir.IdentifiedStructType] = {}
        self.atom_struct_defs: Dict[str, ast.StructDef] = {} # Cache das definições AST
        self.atom_enum_defs: Dict[str, ast.EnumDef] = {}     # Cache das definições AST
        self.llvm_global_constants: Dict[str, Tuple[ir.GlobalVariable, ast.Expression]] = {} # Mapeia nome -> (GlobalVar, Nó AST do valor)
        self.loop_context_stack: List[Tuple[ir.Block, ir.Block]] = [] # Pilha para break/continue (cond/header, end)
        # --- Fim das inicializações ---

    def type_to_string(self, type_node: Optional[Union[ast.Type, ir.Type]]) -> str:
         if type_node is None: return "<desconhecido>"
         if isinstance(type_node, ast.Node): return repr(type_node)
         elif isinstance(type_node, ir.Type): return str(type_node)
         else: return f"<tipo_invalido:{type(type_node).__name__}>"

    def is_integer_type(self, llvm_type: Optional[ir.Type]) -> bool:
         return isinstance(llvm_type, ir.IntType)

    def is_signed_type_heuristic(self, atom_type: Optional[ast.Type], llvm_type: Optional[ir.Type]) -> bool:
        if isinstance(atom_type, ast.PrimitiveType):
             return atom_type.name.startswith('i') or atom_type.name in ('int', 'isize')
        elif isinstance(atom_type, ast.LiteralIntegerType):
             return atom_type.value < 0
        elif isinstance(llvm_type, ir.IntType):
             known_signed_llvm_types = [
                 self.llvm_types.get(name) for name in
                 ('i8', 'i16', 'i32', 'i64', 'isize', 'int') if name in self.llvm_types
             ]
             return llvm_type in known_signed_llvm_types
        return False

    def get_llvm_type(self, atom_type: Optional[ast.Type]) -> Optional[ir.Type]:
        if atom_type is None: return None
        if isinstance(atom_type, ast.PrimitiveType):
            llvm_t = self.llvm_types.get(atom_type.name)
            if llvm_t is None: self.add_error(f"Tipo LLVM desconhecido para primitivo Atom '{atom_type.name}'.", atom_type)
            return llvm_t
        if isinstance(atom_type, ast.UnitType):
            return self.llvm_types['unit']
        if isinstance(atom_type, ast.PointerType):
            pointee_llvm_type = self.get_llvm_type(atom_type.pointee_type)
            if pointee_llvm_type is None: self.add_error(f"Falha obter tipo pointee para {atom_type!r}", atom_type.pointee_type); return None
            return ir.PointerType(pointee_llvm_type)
        if isinstance(atom_type, ast.ReferenceType):
            referenced_llvm_type = self.get_llvm_type(atom_type.referenced_type)
            if referenced_llvm_type is None: self.add_error(f"Falha obter tipo referenced para {atom_type!r}", atom_type.referenced_type); return None
            return ir.PointerType(referenced_llvm_type)
        if isinstance(atom_type, ast.ArrayType):
            element_llvm_type = self.get_llvm_type(atom_type.element_type)
            if element_llvm_type is None: self.add_error(f"Falha obter tipo elemento array {atom_type!r}", atom_type.element_type); return None
            array_size: Optional[int] = None
            if isinstance(atom_type.size, ast.IntegerLiteral):
                 array_size = atom_type.size.value
            else:
                 const_size_val = self.evaluate_constant_expression(atom_type.size, self.llvm_types.get('usize'))
                 if isinstance(const_size_val, ir.Constant) and isinstance(const_size_val.type, ir.IntType):
                     array_size = const_size_val.constant
                 else:
                     self.add_error(f"Tamanho de array não constante/avaliável: {atom_type.size!r}", atom_type.size)
                     return None
            if array_size is not None and array_size >= 0:
                return ir.ArrayType(element_llvm_type, array_size)
            else: self.add_error(f"Tamanho inválido para array {atom_type!r}", atom_type.size); return None
        if isinstance(atom_type, ast.SliceType):
            element_llvm_type = self.get_llvm_type(atom_type.element_type)
            if element_llvm_type is None: self.add_error(f"Falha obter tipo elemento slice {atom_type!r}", atom_type.element_type); return None
            ptr_type = ir.PointerType(element_llvm_type)
            len_type = self.llvm_types['usize']
            element_type_str_for_name = str(element_llvm_type)
            for char_to_replace in ['%', '*', '[', ']', ';', ',']: element_type_str_for_name = element_type_str_for_name.replace(char_to_replace, "")
            element_type_str_for_name = element_type_str_for_name.replace(" ", "_")
            slice_struct_name = f"Slice.{element_type_str_for_name}"
            if slice_struct_name in self.module.context.identified_types:
                 slice_llvm_type = self.module.context.identified_types[slice_struct_name]
                 if slice_llvm_type.is_opaque: slice_llvm_type.set_body(ptr_type, len_type)
                 elif tuple(slice_llvm_type.elements) != (ptr_type, len_type): return ir.LiteralStructType([ptr_type, len_type])
                 return slice_llvm_type
            else:
                 slice_llvm_type = self.module.context.get_identified_type(slice_struct_name)
                 slice_llvm_type.set_body(ptr_type, len_type)
                 return slice_llvm_type
        if isinstance(atom_type, ast.CustomType):
            type_name = atom_type.name.name
            if type_name in self.llvm_defined_structs: return self.llvm_defined_structs[type_name]
            elif type_name in self.atom_enum_defs:
                i32_type = self.llvm_types.get('i32')
                if not i32_type: self.add_error("FATAL: Tipo i32 não definido em llvm_types para Enum.", atom_type); return None
                return i32_type
            else: self.add_error(f"Tipo customizado '{type_name}' não encontrado.", atom_type); return None
        if isinstance(atom_type, ast.FunctionType):
            llvm_ret_type = self.get_llvm_type(atom_type.return_type)
            if llvm_ret_type is None: self.add_error(f"Falha obter tipo LLVM retorno para FunctionType.", atom_type); return None
            llvm_param_types = []
            for i, p_type in enumerate(atom_type.param_types):
                llvm_p_type = self.get_llvm_type(p_type)
                if llvm_p_type is None: self.add_error(f"Falha obter tipo LLVM param {i} para FunctionType.", p_type); return None
                llvm_param_types.append(llvm_p_type)
            llvm_func_type = ir.FunctionType(llvm_ret_type, llvm_param_types, var_arg=atom_type.is_var_arg)
            return ir.PointerType(llvm_func_type)
        self.add_error(f"Tipo Atom não suportado em get_llvm_type: {type(atom_type)}", atom_type)
        return None

    def get_concrete_type(self, type_node: Optional[Union[ast.Type, ir.Type]]) -> Optional[ir.Type]:
        if isinstance(type_node, ast.LiteralIntegerType):
            llvm_prim_type = self.llvm_types.get(type_node.default_type_name)
            if not isinstance(llvm_prim_type, ir.IntType): return None
            return llvm_prim_type
        elif isinstance(type_node, ast.Type): return self.get_llvm_type(type_node)
        elif isinstance(type_node, ir.Type): return type_node
        return None

    def enter_scope(self): self.llvm_symbol_table.append({})
    def exit_scope(self):
        if len(self.llvm_symbol_table) > 1: self.llvm_symbol_table.pop()
        else: print("WARN Scope: Attempt to exit global scope!")

    def declare_var(self, name: str, llvm_value: ir.Value):
        if not isinstance(llvm_value.type, ir.PointerType):
             print(f"WARN Scope: Tentando declarar valor não-ponteiro '{name}' (tipo: {llvm_value.type}) na tabela LLVM.")
        self.llvm_symbol_table[-1][name] = llvm_value

    def lookup_var(self, name: str) -> Optional[ir.Value]:
        for scope in reversed(self.llvm_symbol_table):
            if name in scope: return scope[name]
        return None

    def add_error(self, message: str, node: Optional[ast.Node] = None):
        pos_info = "";detail = ""
        if node and hasattr(node, 'meta') and hasattr(node.meta, 'line'):
             pos_info = f" (linha {node.meta.line}, col {getattr(node.meta, 'column', '?')})"
        print(f"CODEGEN ERROR:{pos_info} {message}{detail}")

    # Helper para inferir sinal de constantes (similar ao de runtime)
    def is_signed_constant_heuristic(self, const_val: ir.Constant, 
                                     expected_llvm_type: Optional[ir.Type] = None) -> bool:
        const_type = const_val.type
        if not isinstance(const_type, ir.IntType):
            return False # Não é inteiro

        # Tenta usar o tipo esperado se fornecer informação de sinal
        if isinstance(expected_llvm_type, ir.IntType):
             known_signed_llvm_types = [
                 self.llvm_types.get(name) for name in
                 ('i8', 'i16', 'i32', 'i64', 'isize', 'int') if name in self.llvm_types
             ]
             if expected_llvm_type in known_signed_llvm_types:
                 return True
             known_unsigned_llvm_types = [
                 self.llvm_types.get(name) for name in
                 ('u8', 'u16', 'u32', 'u64', 'usize', 'uint', 'char', 'bool') if name in self.llvm_types
             ]
             if expected_llvm_type in known_unsigned_llvm_types:
                  return False
                  
        # Fallback: verifica se o próprio tipo da constante corresponde a um tipo signed conhecido
        # (menos confiável, pois um u32 pode ter vindo de um literal negativo no código fonte)
        known_signed_llvm_types_fallback = [
            self.llvm_types.get(name) for name in
            ('i8', 'i16', 'i32', 'i64', 'isize', 'int') if name in self.llvm_types
        ]
        return const_type in known_signed_llvm_types_fallback
    
    # Função atualizada para avaliar expressões constantes
    def evaluate_constant_expression(self, 
                                     node: ast.Expression, 
                                     expected_llvm_type: Optional[ir.Type] = None,
                                     visiting: Optional[Set[int]] = None
                                     ) -> Optional[ir.Constant]:
        if visiting is None: visiting = set()
        node_id = id(node)
        if node_id in visiting:
            self.add_error(f"Detectada dependência cíclica na avaliação da expressão constante.", node)
            return None
        visiting.add(node_id)

        result: Optional[ir.Constant] = None
        try: # Usar try/finally para garantir a remoção do ID
            if isinstance(node, ast.IntegerLiteral):
                llvm_type_to_use: Optional[ir.IntType] = None
                if isinstance(expected_llvm_type, ir.IntType):
                    llvm_type_to_use = expected_llvm_type
                else: # Tenta usar i32 como padrão se não houver tipo esperado
                    llvm_type_to_use = self.llvm_types.get('i32') 
                    
                if not isinstance(llvm_type_to_use, ir.IntType):
                    # Se ainda assim não for IntType (erro interno ou tipo esperado não-int)
                    self.add_error(f"Não foi possível determinar o tipo LLVM inteiro para o literal {node.value}.", node)
                    return None # Retorna None aqui ao invés de levantar exceção

                # Tenta criar a constante. Se o valor não couber, llvmlite pode reclamar.
                try:
                     result = ir.Constant(llvm_type_to_use, node.value)
                except OverflowError:
                     self.add_error(f"Valor do literal inteiro {node.value} fora dos limites para o tipo esperado/inferido {llvm_type_to_use}.", node)
                except Exception as e:
                     self.add_error(f"Erro ao criar constante LLVM para literal inteiro {node.value} (tipo {llvm_type_to_use}): {e}", node)
            
            elif isinstance(node, ast.StringLiteral): 
                # Ponteiro para string global é constante
                result = create_global_string_constant(self.module, node.value)
                # Se o tipo esperado for diferente (e.g., outro tipo de ponteiro), faz bitcast constante
                if expected_llvm_type and result.type != expected_llvm_type:
                     if isinstance(expected_llvm_type, ir.PointerType):
                          try: result = result.bitcast(expected_llvm_type)
                          except Exception as e: self.add_error(f"Falha no bitcast constante de string literal para {expected_llvm_type}: {e}", node); result=None
                     else: self.add_error(f"Tipo esperado {expected_llvm_type} incompatível com ponteiro de string literal.", node); result=None
                
            elif isinstance(node, ast.BooleanLiteral):
                bool_type = self.llvm_types.get('bool')
                if not isinstance(bool_type, ir.IntType) or bool_type.width != 1: 
                    self.add_error("Tipo LLVM 'bool' (i1) não definido corretamente.", node); return None
                result = ir.Constant(bool_type, int(node.value))

            elif isinstance(node, ast.CharLiteral):
                char_type = self.llvm_types.get('char') # Geralmente i8
                if not isinstance(char_type, ir.IntType): 
                    self.add_error("Tipo LLVM 'char' não definido corretamente.", node); return None
                try: 
                     result = ir.Constant(char_type, ord(node.value))
                except TypeError: 
                     self.add_error(f"Valor de char literal inválido: '{node.value}'", node)

            elif isinstance(node, ast.ByteStringLiteral):
                # Retorna um valor de slice constante { ptr, len }
                actual_bytes = node.value
                if not isinstance(actual_bytes, bytes): 
                    self.add_error("Valor de ByteStringLiteral não é bytes.", node); return None
                
                global_byte_array_var = create_global_byte_array_constant(self.module, actual_bytes)
                zero_i32 = ir.Constant(ir.IntType(32), 0)
                # GEP constante para obter o ponteiro para o primeiro byte
                ptr_to_first_byte_const = global_byte_array_var.gep([zero_i32, zero_i32]) 
                
                usize_type = self.llvm_types.get('usize')
                if not usize_type: 
                    self.add_error("Tipo LLVM 'usize' não definido.", node); return None
                len_value_const = ir.Constant(usize_type, len(actual_bytes))
                
                # Determina o tipo LLVM do slice (esperado ou literal)
                ptr_i8_type = ir.PointerType(ir.IntType(8))
                slice_llvm_type_literal = ir.LiteralStructType([ptr_i8_type, usize_type])
                final_slice_type_for_const = slice_llvm_type_literal
                
                if isinstance(expected_llvm_type, ir.StructType) and \
                   hasattr(expected_llvm_type, 'elements') and len(expected_llvm_type.elements) == 2 and \
                   expected_llvm_type.elements[0] == ptr_i8_type and \
                   expected_llvm_type.elements[1] == usize_type:
                    final_slice_type_for_const = expected_llvm_type
                elif expected_llvm_type and expected_llvm_type != slice_llvm_type_literal:
                    # Se o tipo esperado não for um slice compatível, é um erro aqui.
                    self.add_error(f"Byte string literal não pode ser usado como tipo constante esperado '{expected_llvm_type}'.", node)
                    return None

                result = ir.Constant(final_slice_type_for_const, [ptr_to_first_byte_const, len_value_const])

            elif isinstance(node, ast.NamespaceAccess):
                # Avalia variante de enum para seu valor inteiro (i32)
                variant_value = getattr(node, 'resolved_variant_value', None)
                enum_def_node = getattr(node, 'resolved_enum_def_node', None)
                if variant_value is None or not isinstance(enum_def_node, ast.EnumDef): 
                    self.add_error(f"Namespace access '{node!r}' não resolveu para variante de enum válida.", node); return None
                
                i32_type = self.llvm_types.get('i32')
                if not i32_type: self.add_error("Tipo LLVM i32 não definido.", node); return None
                
                result = ir.Constant(i32_type, variant_value)
                # Cast constante se o tipo esperado for diferente (mas compatível, ex: u32)
                if expected_llvm_type and result.type != expected_llvm_type:
                    if isinstance(expected_llvm_type, ir.IntType) and result.type.width == expected_llvm_type.width:
                         try: result = result.bitcast(expected_llvm_type)
                         except Exception: self.add_error(f"Falha no bitcast constante de enum para {expected_llvm_type}", node); result=None
                    elif isinstance(expected_llvm_type, ir.IntType):
                        op = 'zext' if expected_llvm_type.width > result.type.width else 'trunc'
                        try: result = getattr(result, op)(expected_llvm_type)
                        except Exception: self.add_error(f"Falha no {op} constante de enum para {expected_llvm_type}", node); result=None
                    else: self.add_error(f"Tipo esperado {expected_llvm_type} incompatível com valor de enum (i32).", node); result=None

            elif isinstance(node, ast.Identifier):
                # Avalia referência a outra constante global
                const_name = node.name
                if const_name in self.llvm_global_constants:
                     gvar, value_node_orig_ast = self.llvm_global_constants[const_name]
                     
                     # Se já foi avaliada (cuidado com recursão mútua se não usar 'visiting')
                     if gvar.initializer is not None and not isinstance(gvar.initializer, type(ir.Undefined)):
                          result = gvar.initializer
                     else:
                          # Avalia a constante referenciada recursivamente
                          ref_expected_type = gvar.type.pointee 
                          # Passa o set 'visiting' para detectar ciclos
                          dep_const_val = self.evaluate_constant_expression(value_node_orig_ast, ref_expected_type, visiting)
                          
                          if dep_const_val is None: return None # Falha ao avaliar dependência
                          
                          # Verifica tipo e faz cast constante se necessário para o tipo da GVar
                          final_dep_val_for_gvar = dep_const_val
                          if dep_const_val.type != ref_expected_type:
                              casted_for_gvar = None
                              if isinstance(dep_const_val.type, ir.IntType) and isinstance(ref_expected_type, ir.IntType):
                                   op = 'sext' if self.is_signed_constant_heuristic(dep_const_val, dep_const_val.type) and ref_expected_type.width > dep_const_val.type.width else \
                                        'zext' if ref_expected_type.width > dep_const_val.type.width else \
                                        'trunc' if ref_expected_type.width < dep_const_val.type.width else 'bitcast'
                                   try: casted_for_gvar = getattr(dep_const_val, op)(ref_expected_type)
                                   except Exception: pass
                              elif isinstance(dep_const_val.type, ir.PointerType) and isinstance(ref_expected_type, ir.PointerType):
                                   try: casted_for_gvar = dep_const_val.bitcast(ref_expected_type)
                                   except Exception: pass
                                   
                              if casted_for_gvar: final_dep_val_for_gvar = casted_for_gvar
                              else: self.add_error(f"Tipo constante avaliado ({dep_const_val.type}) da dependência '{const_name}' incompatível com tipo da constante ({ref_expected_type}).", node); return None
                                   
                          gvar.initializer = final_dep_val_for_gvar
                          result = gvar.initializer
                          
                     # Após obter o valor da constante referenciada, faz cast se o contexto atual esperar outro tipo
                     if result and expected_llvm_type and result.type != expected_llvm_type:
                          casted_final_val = None
                          if isinstance(result.type, ir.IntType) and isinstance(expected_llvm_type, ir.IntType):
                               op = 'sext' if self.is_signed_constant_heuristic(result, result.type) and expected_llvm_type.width > result.type.width else \
                                    'zext' if expected_llvm_type.width > result.type.width else \
                                    'trunc' if expected_llvm_type.width < result.type.width else 'bitcast'
                               try: casted_final_val = getattr(result, op)(expected_llvm_type)
                               except Exception: pass
                          elif isinstance(result.type, ir.PointerType) and isinstance(expected_llvm_type, ir.PointerType):
                               try: casted_final_val = result.bitcast(expected_llvm_type)
                               except Exception: pass
                               
                          if casted_final_val: result = casted_final_val
                          else: self.add_error(f"Tipo da constante '{const_name}' ({result.type}) incompatível com tipo esperado ({expected_llvm_type}).", node); result=None
                else:
                    self.add_error(f"Identificador '{const_name}' não é uma constante global conhecida.", node)
            
            # --- Blocos Novos/Atualizados ---

            elif isinstance(node, ast.UnaryOp):
                # Avalia operando
                operand_const = self.evaluate_constant_expression(node.operand, None, visiting) # Não propaga expected_type para operando unário
                if operand_const:
                    op = node.op
                    try:
                        if op == '!' and isinstance(operand_const.type, ir.IntType): # Lógico ou Bitwise NOT
                            result = operand_const.not_()
                        elif op == '-' and isinstance(operand_const.type, ir.IntType): # Negação aritmética
                            result = operand_const.neg()
                        elif op == '~' and isinstance(operand_const.type, ir.IntType): # Bitwise NOT
                            result = operand_const.not_()
                        # Operadores &,&mut,* não são aplicáveis em contexto constante de valor
                        else: self.add_error(f"Operador unário constante '{op}' não suportado.", node)
                    except Exception as e: self.add_error(f"Erro ao avaliar operador unário constante '{op}': {e}", node)

            elif isinstance(node, ast.BinaryOp):
                # Avalia operandos
                # Tenta passar o expected_llvm_type para os operandos, pode ajudar na inferência
                left_const = self.evaluate_constant_expression(node.left, expected_llvm_type, visiting)
                right_const = self.evaluate_constant_expression(node.right, expected_llvm_type, visiting)

                if left_const and right_const:
                    op = node.op
                    # Tenta garantir tipos compatíveis (ex: ambos i32) antes da operação LLVM
                    # (LLVM pode lidar com alguns mismatches, mas ser explícito é mais seguro)
                    # Simplificação: Se os tipos não forem iguais, tenta bitcast se forem inteiros de mesma largura.
                    # Uma promoção mais robusta (zext/sext) seria ideal mas complexa aqui.
                    if left_const.type != right_const.type:
                         if isinstance(left_const.type, ir.IntType) and isinstance(right_const.type, ir.IntType) and left_const.type.width == right_const.type.width:
                              try: right_const = right_const.bitcast(left_const.type)
                              except Exception: pass # Deixa como está se o bitcast falhar
                         # Não tenta operar se os tipos forem fundamentalmente diferentes após tentativa de bitcast
                         if left_const.type != right_const.type:
                              self.add_error(f"Tipos incompatíveis ({left_const.type} vs {right_const.type}) para operação binária constante '{op}'.", node)
                              left_const = None # Invalida para evitar erro abaixo
                              
                    if left_const and right_const: # Checa novamente após ajuste de tipo
                        target_type = left_const.type # Usa o tipo (ajustado) do operando esquerdo
                        is_signed = self.is_signed_constant_heuristic(left_const, target_type)
                        
                        try:
                            if op == '+': result = left_const.add(right_const)
                            elif op == '-': result = left_const.sub(right_const)
                            elif op == '*': result = left_const.mul(right_const)
                            elif op == '/':
                                if int(right_const.constant) == 0: self.add_error("Divisão constante por zero.", node)
                                else: result = left_const.sdiv(right_const) if is_signed else left_const.udiv(right_const)
                            elif op == '%':
                                if int(right_const.constant) == 0: self.add_error("Módulo constante por zero.", node)
                                else: result = left_const.srem(right_const) if is_signed else left_const.urem(right_const)
                            elif op == '&': result = left_const.and_(right_const)
                            elif op == '|': result = left_const.or_(right_const)
                            elif op == '^': result = left_const.xor(right_const)
                            elif op == '<<': result = left_const.shl(right_const)
                            elif op == '>>': result = left_const.ashr(right_const) if is_signed else left_const.lshr(right_const)
                            elif op in ('==', '!=', '<', '>', '<=', '>='):
                                 # Determina predicado icmp
                                 icmp_pred = op # Para ==, !=
                                 if op == '<': icmp_pred = 'slt' if is_signed else 'ult'
                                 elif op == '>': icmp_pred = 'sgt' if is_signed else 'ugt'
                                 elif op == '<=': icmp_pred = 'sle' if is_signed else 'ule'
                                 elif op == '>=': icmp_pred = 'sge' if is_signed else 'uge'
                                 result = left_const.icmp_signed(icmp_pred, right_const) if is_signed else left_const.icmp_unsigned(icmp_pred, right_const)
                            # Não suporta &&, || diretamente em evaluate (requer fluxo de controle)
                            else: self.add_error(f"Operador binário constante '{op}' não suportado na avaliação.", node)
                        except OverflowError: self.add_error(f"Overflow na avaliação constante de '{op}'.", node)
                        except Exception as e: self.add_error(f"Erro ao avaliar operador binário constante '{op}': {e}", node)

            elif isinstance(node, ast.CastExpr):
                 source_const = self.evaluate_constant_expression(node.expr, None, visiting) # Avalia a expressão interna
                 if source_const:
                     target_llvm_type = self.get_llvm_type(node.target_type) # Obtém o tipo LLVM de destino
                     if target_llvm_type:
                         source_llvm_type = source_const.type
                         try:
                             if source_llvm_type == target_llvm_type: result = source_const # Sem necessidade de cast
                             elif isinstance(source_llvm_type, ir.IntType) and isinstance(target_llvm_type, ir.IntType):
                                 src_w = source_llvm_type.width; tgt_w = target_llvm_type.width
                                 if tgt_w < src_w: result = source_const.trunc(target_llvm_type)
                                 elif tgt_w > src_w:
                                     is_signed = self.is_signed_constant_heuristic(source_const, source_llvm_type)
                                     result = source_const.sext(target_llvm_type) if is_signed else source_const.zext(target_llvm_type)
                                 else: result = source_const.bitcast(target_llvm_type)
                             elif isinstance(source_llvm_type, ir.PointerType) and isinstance(target_llvm_type, ir.PointerType):
                                  result = source_const.bitcast(target_llvm_type)
                             elif isinstance(source_llvm_type, ir.IntType) and isinstance(target_llvm_type, ir.PointerType):
                                  result = source_const.inttoptr(target_llvm_type)
                             elif isinstance(source_llvm_type, ir.PointerType) and isinstance(target_llvm_type, ir.IntType):
                                  result = source_const.ptrtoint(target_llvm_type)
                             else: self.add_error(f"Cast constante de '{source_llvm_type}' para '{target_llvm_type}' não suportado.", node)
                         except Exception as e: self.add_error(f"Erro ao realizar cast constante: {e}", node)
                     else: self.add_error(f"Tipo alvo do cast '{node.target_type!r}' inválido.", node.target_type)
                 
            elif isinstance(node, ast.FieldAccess):
                 obj_const = self.evaluate_constant_expression(node.obj, None, visiting)
                 if isinstance(obj_const, ir.Constant) and isinstance(obj_const.type, ir.StructType):
                     # Precisa do AST original para obter o índice do campo
                     obj_type_ast = getattr(node.obj, 'atom_type', None)
                     obj_type_resolved = self.analyzer.get_concrete_type(obj_type_ast) if hasattr(self, 'analyzer') else None # Precisa de acesso ao analyzer
                     
                     if isinstance(obj_type_resolved, ast.CustomType):
                          struct_name = obj_type_resolved.name.name
                          struct_def_node = self.atom_struct_defs.get(struct_name) # Usa cache do codegen
                          if struct_def_node:
                               field_name_to_find = node.field.name
                               field_index = -1
                               for i, f_def in enumerate(struct_def_node.fields):
                                   if f_def.name.name == field_name_to_find:
                                       field_index = i; break
                               if field_index != -1 and field_index < len(obj_const.operands):
                                   result = obj_const.operands[field_index]
                               else: self.add_error(f"Índice de campo inválido ou fora dos limites para '{field_name_to_find}' em struct constante.", node.field)
                          else: self.add_error(f"Definição AST do struct '{struct_name}' não encontrada para acesso a campo constante.", node.obj)
                     else: self.add_error("Tipo do objeto base para acesso a campo constante não é um CustomType conhecido.", node.obj)
                 elif obj_const: self.add_error(f"Acesso a campo constante em tipo não-struct '{obj_const.type}'.", node.obj)

            elif isinstance(node, ast.IndexAccess):
                 array_const = self.evaluate_constant_expression(node.array, None, visiting)
                 index_const = self.evaluate_constant_expression(node.index, self.llvm_types.get('usize'), visiting) # Espera usize para índice

                 if isinstance(array_const, ir.Constant) and isinstance(array_const.type, ir.ArrayType) and \
                    isinstance(index_const, ir.Constant) and isinstance(index_const.type, ir.IntType):
                    
                    index_value = int(index_const.constant)
                    array_len = array_const.type.count
                    
                    if 0 <= index_value < array_len:
                         if index_value < len(array_const.operands):
                              result = array_const.operands[index_value]
                         else: self.add_error(f"Erro interno: número de operandos ({len(array_const.operands)}) inconsistente com tamanho do array ({array_len}) para acesso a índice constante.", node)
                    else: self.add_error(f"Índice constante '{index_value}' fora dos limites para array de tamanho '{array_len}'.", node.index)
                 elif array_const and index_const: # Se ambos avaliaram mas não são os tipos certos
                      self.add_error(f"Acesso a índice constante requer array constante e índice inteiro constante. Recebido: array '{array_const.type}', indice '{index_const.type}'.", node)

            # --- Fim Blocos Novos/Atualizados ---

            # Adicione elif para outros nós que podem ser constantes, se houver.
            # ... ArrayLiteral, StructLiteral, ArrayRepeatExpr (já existentes e precisam passar 'visiting') ...
            elif isinstance(node, ast.ArrayLiteral):
                 element_llvm_type: Optional[ir.Type] = None
                 if isinstance(expected_llvm_type, ir.ArrayType): 
                      element_llvm_type = expected_llvm_type.element
                 elif isinstance(expected_llvm_type, ir.PointerType) and isinstance(expected_llvm_type.pointee, ir.ArrayType):
                      element_llvm_type = expected_llvm_type.pointee.element
                 
                 const_elements = []
                 success = True
                 for el_node in node.elements:
                      const_el = self.evaluate_constant_expression(el_node, element_llvm_type, visiting)
                      if const_el is None: success = False; break
                      # Tenta cast se necessário
                      if element_llvm_type and const_el.type != element_llvm_type:
                          # ... (lógica de cast constante similar à de Identifier) ...
                          casted_el = None
                          if isinstance(const_el.type, ir.IntType) and isinstance(element_llvm_type, ir.IntType):
                               op = 'sext' if self.is_signed_constant_heuristic(const_el, const_el.type) and element_llvm_type.width > const_el.type.width else \
                                    'zext' if element_llvm_type.width > const_el.type.width else \
                                    'trunc' if element_llvm_type.width < const_el.type.width else 'bitcast'
                               try: casted_el = getattr(const_el, op)(element_llvm_type)
                               except Exception: pass
                          if casted_el: const_el = casted_el
                          else: self.add_error(f"Elemento de array constante ({const_el.type}) incompatível com tipo esperado ({element_llvm_type}).", el_node); success=False; break
                      const_elements.append(const_el)
                      if element_llvm_type is None and const_elements: # Infer element type from first element
                           element_llvm_type = const_elements[0].type
                           
                 if success:
                      if not const_elements and isinstance(expected_llvm_type, ir.ArrayType):
                           result = ir.Constant(expected_llvm_type, []) # Array vazio constante
                      elif const_elements:
                           final_element_type = const_elements[0].type
                           array_type = ir.ArrayType(final_element_type, len(const_elements))
                           # Verifica se o tipo inferido/construído bate com o esperado
                           if expected_llvm_type and array_type != expected_llvm_type:
                                if isinstance(expected_llvm_type, ir.ArrayType) and expected_llvm_type.count == len(const_elements) and expected_llvm_type.element == final_element_type:
                                    array_type = expected_llvm_type # Usa o tipo nomeado/identificado se compatível
                                else:
                                    self.add_error(f"Tipo do array literal constante inferido ({array_type}) incompatível com tipo esperado ({expected_llvm_type}).", node); result=None; success=False
                           if success:
                                try: result = ir.Constant(array_type, const_elements)
                                except Exception as e: self.add_error(f"Erro ao criar constante array: {e}", node); result = None
            
            elif isinstance(node, ast.StructLiteral):
                 struct_type_name = node.type_name.name
                 llvm_struct_type = self.llvm_defined_structs.get(struct_type_name)
                 if not isinstance(llvm_struct_type, ir.IdentifiedStructType) or llvm_struct_type.is_opaque: 
                      self.add_error(f"Tipo struct '{struct_type_name}' não definido ou opaco para literal constante.", node.type_name); return None
                 
                 struct_def_node_ast = self.atom_struct_defs.get(struct_type_name)
                 if not struct_def_node_ast or len(node.fields) != len(struct_def_node_ast.fields): 
                      self.add_error(f"Número incorreto de campos para literal constante de struct '{struct_type_name}'.", node); return None
                      
                 literal_fields_map_ast = {f.name.name: f.value for f in node.fields}
                 const_field_values = []
                 is_ok = True
                 for i, field_def_ast in enumerate(struct_def_node_ast.fields):
                     field_name = field_def_ast.name.name
                     field_llvm_type_expected = llvm_struct_type.elements[i]
                     
                     if field_name not in literal_fields_map_ast: 
                          self.add_error(f"Campo '{field_name}' faltando no literal constante de struct '{struct_type_name}'.", node); is_ok = False; break
                          
                     field_value_node_ast = literal_fields_map_ast[field_name]
                     # Passa o tipo esperado do campo para avaliação recursiva
                     const_field_val = self.evaluate_constant_expression(field_value_node_ast, field_llvm_type_expected, visiting)
                     if const_field_val is None: is_ok = False; break # Erro já reportado recursivamente
                     
                     # Verifica tipo e faz cast constante se necessário
                     if const_field_val.type != field_llvm_type_expected:
                          casted_field_val = None
                          # ... (lógica de cast constante similar à de Identifier/ArrayLiteral) ...
                          if isinstance(const_field_val.type, ir.IntType) and isinstance(field_llvm_type_expected, ir.IntType):
                               op = 'sext' if self.is_signed_constant_heuristic(const_field_val, const_field_val.type) and field_llvm_type_expected.width > const_field_val.type.width else \
                                    'zext' if field_llvm_type_expected.width > const_field_val.type.width else \
                                    'trunc' if field_llvm_type_expected.width < const_field_val.type.width else 'bitcast'
                               try: casted_field_val = getattr(const_field_val, op)(field_llvm_type_expected)
                               except Exception: pass
                          elif isinstance(const_field_val.type, ir.PointerType) and isinstance(field_llvm_type_expected, ir.PointerType):
                               try: casted_field_val = const_field_val.bitcast(field_llvm_type_expected)
                               except Exception: pass
                               
                          if casted_field_val: const_field_val = casted_field_val
                          else: self.add_error(f"Tipo do campo constante '{field_name}' ({const_field_val.type}) incompatível com tipo esperado ({field_llvm_type_expected}).", field_value_node_ast); is_ok = False; break
                          
                     const_field_values.append(const_field_val)
                     
                 if is_ok: 
                      try: result = ir.Constant(llvm_struct_type, const_field_values)
                      except Exception as e: self.add_error(f"Erro ao criar constante struct: {e}", node); result=None

            elif isinstance(node, ast.ArrayRepeatExpr):
                 if not isinstance(expected_llvm_type, ir.ArrayType): 
                      self.add_error("Tipo esperado para array repeat constante não é um tipo array.", node); return None
                      
                 # Avalia o tamanho constante
                 size_const = self.evaluate_constant_expression(node.size, self.llvm_types.get('usize'), visiting)
                 if not (isinstance(size_const, ir.Constant) and isinstance(size_const.type, ir.IntType)):
                     self.add_error("Tamanho de array repeat constante não pôde ser avaliado como inteiro constante.", node.size); return None
                 const_size = int(size_const.constant)
                 
                 if const_size < 0: self.add_error("Tamanho de array repeat constante não pode ser negativo.", node.size); return None
                 if const_size != expected_llvm_type.count: 
                      self.add_error(f"Tamanho avaliado ({const_size}) de array repeat constante diferente do tamanho esperado ({expected_llvm_type.count}).", node.size); return None
                      
                 expected_elem_type = expected_llvm_type.element
                 # Avalia o valor a repetir
                 const_val_to_repeat = self.evaluate_constant_expression(node.value, expected_elem_type, visiting)
                 if const_val_to_repeat is None: return None # Erro já reportado
                 
                 # Verifica e casta o valor a repetir se necessário
                 if const_val_to_repeat.type != expected_elem_type:
                      casted_repeat_val = None
                      # ... (lógica de cast constante similar à de StructLiteral) ...
                      if isinstance(const_val_to_repeat.type, ir.IntType) and isinstance(expected_elem_type, ir.IntType):
                           op = 'sext' # ... etc ...
                           try: casted_repeat_val = getattr(const_val_to_repeat, op)(expected_elem_type)
                           except Exception: pass
                      if casted_repeat_val: const_val_to_repeat = casted_repeat_val
                      else: self.add_error(f"Tipo do valor a repetir ({const_val_to_repeat.type}) incompatível com tipo esperado do elemento ({expected_elem_type}).", node.value); return None

                 # Cria a lista de elementos repetidos
                 elements = [const_val_to_repeat] * const_size
                 try: result = ir.Constant(expected_llvm_type, elements)
                 except Exception as e: self.add_error(f"Erro ao criar constante array repeat: {e}", node); result=None
                 
            else:
                 # Se chegou aqui, is_constant_expression retornou True, mas não sabemos avaliar
                 self.add_error(f"Avaliação de constante não implementada para o nó: {type(node).__name__}", node)

        finally:
             visiting.remove(node_id) # Garante que removemos o ID do set

        return result


    # --- Passagens de Geração de Código ---
    def generate_code(self, node: ast.Program) -> str:
        print("--- CodeGen Pass 1: Declarations ---")
        for item in node.body:
            if isinstance(item, ast.StructDef): self.declare_struct_type(item)
            elif isinstance(item, ast.EnumDef): self.declare_enum_type(item)
            elif isinstance(item, ast.FunctionDef): self.declare_function_signature(item)
            elif isinstance(item, ast.ExternBlock): self.visit_ExternBlock(item)
            elif isinstance(item, ast.ConstDef): self.declare_const_global(item)
            elif isinstance(item, ast.ImportDecl): print(f"WARN CodeGen: ImportDecl não implementado.")
            else: self.add_error(f"Item top-level inesperado na Passagem 1: {type(item)}", item)

        print("--- CodeGen Pass 2: Struct Bodies ---")
        for struct_def_node in self.atom_struct_defs.values():
            self.define_struct_body(struct_def_node)

        print("--- CodeGen Pass 3: Constant Initializers ---")
        processed_constants = set()
        # ... (lógica de inicialização de constantes como antes) ...
        for _ in range(len(self.llvm_global_constants) + 1):
            all_resolved_this_pass = True
            for const_name, (gvar, value_node_ast) in self.llvm_global_constants.items():
                if const_name in processed_constants or gvar.initializer is not None: continue
                global_llvm_type = gvar.type.pointee
                llvm_const_value = self.evaluate_constant_expression(value_node_ast, global_llvm_type)
                if llvm_const_value:
                    if llvm_const_value.type == global_llvm_type: gvar.initializer = llvm_const_value
                    # ... (outros casts constantes) ...
                    elif isinstance(global_llvm_type, ir.IdentifiedStructType) and isinstance(llvm_const_value.type, ir.LiteralStructType) and len(global_llvm_type.elements) == len(llvm_const_value.type.elements) and all(global_llvm_type.elements[i] == llvm_const_value.type.elements[i] for i in range(len(global_llvm_type.elements))):
                        try: gvar.initializer = ir.Constant(global_llvm_type, llvm_const_value.operands)
                        except Exception: gvar.initializer = ir.Constant(global_llvm_type, None)
                    elif isinstance(llvm_const_value.type, ir.PointerType) and isinstance(global_llvm_type, ir.PointerType):
                        try: gvar.initializer = llvm_const_value.bitcast(global_llvm_type)
                        except Exception: gvar.initializer = ir.Constant(global_llvm_type, None)
                    elif isinstance(llvm_const_value.type, ir.IntType) and isinstance(global_llvm_type, ir.IntType):
                        try:
                            if global_llvm_type.width > llvm_const_value.type.width: gvar.initializer = llvm_const_value.zext(global_llvm_type)
                            elif global_llvm_type.width < llvm_const_value.type.width: gvar.initializer = llvm_const_value.trunc(global_llvm_type)
                            else: gvar.initializer = llvm_const_value
                        except Exception: gvar.initializer = ir.Constant(global_llvm_type, None)
                    else: self.add_error(...); gvar.initializer = ir.Constant(global_llvm_type, None)
                    if gvar.initializer is not None and not isinstance(gvar.initializer, type(ir.Undefined)): processed_constants.add(const_name)
                    else: all_resolved_this_pass = False
                else: all_resolved_this_pass = False
            if all_resolved_this_pass and len(processed_constants) == len(self.llvm_global_constants): break
        for const_name, (gvar, _) in self.llvm_global_constants.items():
            if gvar.initializer is None: self.add_error(...); gvar.initializer = ir.Constant(gvar.type.pointee, None)


        print("--- CodeGen Pass 4: Function Bodies ---")
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                # <<< IMPORTANTE: Atualiza current_function_name aqui >>>
                self.current_function_name = item.name.name
                self.define_function_body(item)
                self.current_function_name = None # Limpa após gerar o corpo
        print("--- CodeGen Finished ---")
        try:
            return str(self.module)
        except Exception as e_str:
             self.add_error(f"Falha ao converter módulo LLVM para string: {e_str}")
             traceback.print_exc()
             return f"; ERRO NA GERAÇÃO FINAL DO IR: {e_str}"

    def declare_struct_type(self, node: ast.StructDef):
        # ... (código como antes) ...
        struct_name = node.name.name
        if struct_name not in self.llvm_defined_structs:
            self.llvm_defined_structs[struct_name] = self.module.context.get_identified_type(struct_name)
        self.atom_struct_defs[struct_name] = node

    def declare_enum_type(self, node: ast.EnumDef):
        # ... (código como antes) ...
        enum_name = node.name.name
        if enum_name in self.atom_enum_defs: return
        self.atom_enum_defs[enum_name] = node

    def declare_function_signature(self, node: Union[ast.FunctionDef, ast.FunctionDecl]):
        # ... (código como antes) ...
         func_name = node.name.name
         if func_name in self.module.globals:
              existing_func = self.module.globals[func_name]
              if isinstance(existing_func, ir.Function): return
              else: self.add_error(...); return
         return_type_llvm = self.get_llvm_type(node.return_type)
         if return_type_llvm is None: self.add_error(...); return
         param_types_llvm = []
         for i_param, param_ast in enumerate(node.params):
             llvm_param_type = self.get_llvm_type(param_ast.type)
             if llvm_param_type is None: self.add_error(...); return
             param_types_llvm.append(llvm_param_type)
         is_vararg = getattr(node, 'is_var_arg', False)
         func_type = ir.FunctionType(return_type_llvm, param_types_llvm, var_arg=is_vararg)
         llvm_func = ir.Function(self.module, func_type, name=func_name)
         for i, arg_llvm in enumerate(llvm_func.args):
              if i < len(node.params): arg_llvm.name = node.params[i].name.name
              else: arg_llvm.name = f"arg{i}"
         self.llvm_symbol_table[0][func_name] = llvm_func

    def visit_ExternBlock(self, node: ast.ExternBlock):
        # ... (código como antes) ...
        for func_decl in node.declarations:
            self.declare_function_signature(func_decl)

    def declare_const_global(self, node: ast.ConstDef):
        # ... (código como antes) ...
        const_name = node.name.name
        if const_name in self.module.globals: return
        llvm_type = self.get_llvm_type(node.type_annot)
        if llvm_type is None: self.add_error(...); return
        gvar = ir.GlobalVariable(self.module, llvm_type, name=const_name)
        gvar.linkage = "internal"; gvar.global_constant = True
        self.llvm_global_constants[const_name] = (gvar, node.value)

    def define_struct_body(self, node: ast.StructDef):
        # ... (código como antes) ...
         struct_name = node.name.name
         if struct_name not in self.llvm_defined_structs: self.add_error(...); return
         llvm_struct_type = self.llvm_defined_structs[struct_name]
         if not llvm_struct_type.is_opaque: return
         field_types_llvm = []
         for field_ast in node.fields:
              llvm_field_type = self.get_llvm_type(field_ast.type)
              if llvm_field_type is None: self.add_error(...); return
              field_types_llvm.append(llvm_field_type)
         llvm_struct_type.set_body(*field_types_llvm)

    def visit_IntegerLiteral(self, node: ast.IntegerLiteral, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
        # ... (código como antes) ...
        llvm_type_to_use: Optional[ir.IntType] = None
        if isinstance(expected_llvm_type, ir.IntType): llvm_type_to_use = expected_llvm_type
        else:
            default_type_name_from_ast = 'i32'
            if isinstance(node, ast.LiteralIntegerType): default_type_name_from_ast = node.default_type_name
            found_type = self.llvm_types.get(default_type_name_from_ast)
            if isinstance(found_type, ir.IntType): llvm_type_to_use = found_type
            else: llvm_type_to_use = self.llvm_types.get('i32')
        if not isinstance(llvm_type_to_use, ir.IntType): self.add_error(...); return None
        try: return ir.Constant(llvm_type_to_use, node.value)
        except Exception as e: self.add_error(...); return None

    def visit_StringLiteral(self, node: ast.StringLiteral, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
        # ... (código como antes) ...
        llvm_ptr_val = create_global_string_constant(self.module, node.value)
        if isinstance(expected_llvm_type, ir.PointerType) and llvm_ptr_val.type != expected_llvm_type:
             if not self.builder: self.add_error(...); return llvm_ptr_val
             return self.builder.bitcast(llvm_ptr_val, expected_llvm_type)
        return llvm_ptr_val

    def visit_BooleanLiteral(self, node: ast.BooleanLiteral, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
        # ... (código como antes) ...
        bool_type = self.llvm_types.get('bool')
        if not isinstance(bool_type, ir.IntType) or bool_type.width != 1: self.add_error(...); return None
        return ir.Constant(bool_type, 1 if node.value else 0)

    def visit_CharLiteral(self, node: ast.CharLiteral, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
        # ... (código como antes) ...
        char_type = self.llvm_types.get('char')
        if not isinstance(char_type, ir.IntType): self.add_error(...); return None
        try: return ir.Constant(char_type, ord(node.value))
        except TypeError: self.add_error(...); return None

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # >>> visit_lvalue_pointer COM ABORDAGEM 8 (CHAMADA HELPER C) <<<
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    def visit_lvalue_pointer(self, node: ast.Expression, allow_immutable_ref: bool = False) -> Optional[ir.Value]:
        # print(f"DEBUG CodeGen: visit_lvalue_pointer para {type(node).__name__} (Nó: {node!r})")
        if not self.builder:
            self.add_error(f"Builder inativo em visit_lvalue_pointer para {type(node).__name__}.", node)
            return None

        # --- CASO IDENTIFIER ---
        if isinstance(node, ast.Identifier):
            var_name = node.name
            llvm_ptr_or_func = self.lookup_var(var_name)
            if llvm_ptr_or_func is not None:
                if isinstance(llvm_ptr_or_func, ir.Function):
                    self.add_error(f"'{var_name}' é uma função e não pode ser usada como L-Value.", node); return None
                if not isinstance(llvm_ptr_or_func.type, ir.PointerType):
                    self.add_error(f"Erro Interno: Símbolo '{var_name}' não é ponteiro.", node); return None
                return llvm_ptr_or_func # Retorna o ponteiro (alloca)
            else: # Verifica globais
                llvm_global = self.module.globals.get(var_name)
                if isinstance(llvm_global, ir.GlobalVariable):
                    return llvm_global # Retorna o ponteiro para a global
                elif isinstance(llvm_global, ir.Function):
                     self.add_error(f"'{var_name}' é uma função global.", node); return None
                else:
                    self.add_error(f"Identificador L-Value não encontrado: '{var_name}'", node); return None

        # --- CASO FIELD ACCESS ---
        elif isinstance(node, ast.FieldAccess):
            field_name = node.field.name
            llvm_base_obj_ptr = self.visit_lvalue_pointer(node.obj)
            if llvm_base_obj_ptr is None: return None
            if not isinstance(llvm_base_obj_ptr.type, ir.PointerType):
                self.add_error(f"Base de FieldAccess não é ponteiro.", node.obj); return None

            type_pointed_to_by_base_ptr = llvm_base_obj_ptr.type.pointee
            ptr_for_gep = llvm_base_obj_ptr
            container_llvm_type = type_pointed_to_by_base_ptr

            if isinstance(type_pointed_to_by_base_ptr, ir.PointerType): # Auto-deref de ponteiro para struct/slice
                 load_name = getattr(node.obj, 'name', 'ptr') + ".load" if isinstance(node.obj, ast.Identifier) else "ptr.load"
                 # Só carrega se o builder estiver ativo
                 if not self.builder or not self.builder.block or self.builder.block.is_terminated:
                     self.add_error("Builder inativo para carregar ponteiro em FieldAccess", node.obj); return None
                 ptr_for_gep = self.builder.load(llvm_base_obj_ptr, name=load_name)
                 if not isinstance(ptr_for_gep.type, ir.PointerType):
                      self.add_error(f"Load de ptr não resultou em ptr.", node.obj); return None
                 container_llvm_type = ptr_for_gep.type.pointee

            zero_const_32 = ir.Constant(ir.IntType(32), 0)
            original_atom_obj_type: Optional[ast.Type] = getattr(node.obj, 'atom_type', None)

            if isinstance(original_atom_obj_type, ast.SliceType): # Slice .len
                if node.field.name == "len":
                    # ... (código para obter ponteiro para .len, como antes) ...
                    if not (isinstance(container_llvm_type, (ir.IdentifiedStructType, ir.LiteralStructType)) and \
                            hasattr(container_llvm_type, 'elements') and len(container_llvm_type.elements) == 2):
                        self.add_error(f"LValue para slice.len, tipo LLVM base '{container_llvm_type}' inválido.", node.obj); return None
                    usize_type_expected = self.llvm_types.get('usize')
                    # ... (verificação do tipo do campo len) ...
                    if not usize_type_expected or not isinstance(container_llvm_type.elements[1], ir.IntType) or \
                       container_llvm_type.elements[1].width != usize_type_expected.width:
                        self.add_error(f"LValue para slice.len, tipo do campo len LLVM incompatível.", node.obj); return None
                    index_const_len = ir.Constant(ir.IntType(32), 1)
                    if not self.builder: self.add_error("Builder inativo para GEP slice.len", node); return None
                    return self.builder.gep(ptr_for_gep, [zero_const_32, index_const_len], name="slice.len.ptr", inbounds=True)
                else:
                    self.add_error(f"Campo '{field_name}' inválido para slice.", node.field); return None
            else: # Struct field
                actual_ast_type_for_struct_lookup = original_atom_obj_type
                if isinstance(original_atom_obj_type, ast.ReferenceType): actual_ast_type_for_struct_lookup = original_atom_obj_type.referenced_type
                elif isinstance(original_atom_obj_type, ast.PointerType): actual_ast_type_for_struct_lookup = original_atom_obj_type.pointee_type

                if isinstance(actual_ast_type_for_struct_lookup, ast.CustomType) and \
                   isinstance(container_llvm_type, (ir.IdentifiedStructType, ir.LiteralStructType)):
                    struct_name_from_atom_type = actual_ast_type_for_struct_lookup.name.name
                    struct_def_node_ast = self.atom_struct_defs.get(struct_name_from_atom_type)
                    if not struct_def_node_ast: self.add_error(...); return None
                    field_index = -1
                    for i, field_def_ast_loop in enumerate(struct_def_node_ast.fields):
                        if field_def_ast_loop.name.name == field_name: field_index = i; break
                    if field_index == -1: self.add_error(...); return None
                    index_const_field = ir.Constant(ir.IntType(32), field_index)
                    if not self.builder: self.add_error("Builder inativo para GEP struct field", node); return None
                    return self.builder.gep(ptr_for_gep, [zero_const_32, index_const_field], name=f"{field_name}.ptr", inbounds=True)
                else:
                    self.add_error(f"Base de FieldAccess não é slice nem struct.", node.obj); return None

        # --- CASO INDEX ACCESS (COM BOUNDS CHECKING - TENTATIVA 8 CORRIGIDA) ---
        elif isinstance(node, ast.IndexAccess):
            # ... (setup inicial, conversão de índice: llvm_index_val) ...
            llvm_base_collection_ptr = self.visit_lvalue_pointer(node.array)
            if llvm_base_collection_ptr is None: return None
            if not isinstance(llvm_base_collection_ptr.type, ir.PointerType): self.add_error(...); return None
            llvm_index_val_expr = self.visit(node.index)
            if llvm_index_val_expr is None: return None
            builder = self.builder
            if not builder or not builder.block or builder.block.is_terminated: self.add_error(...); return None
            usize_type = self.llvm_types.get('usize')
            if not usize_type or not isinstance(usize_type, ir.IntType): self.add_error(...); return None
            llvm_index_val = llvm_index_val_expr
            if llvm_index_val.type != usize_type: # ... (conversão) ...
                if isinstance(llvm_index_val.type, ir.IntType):
                    if usize_type.width > llvm_index_val.type.width: llvm_index_val = builder.zext(llvm_index_val, usize_type, "idx.zext")
                    elif usize_type.width < llvm_index_val.type.width: llvm_index_val = builder.trunc(llvm_index_val, usize_type, "idx.trunc")
                    else: llvm_index_val = builder.bitcast(llvm_index_val, usize_type, "idx.cast")
                else: self.add_error(...); return None

            collection_storage_type = llvm_base_collection_ptr.type.pointee
            zero_const_32 = ir.Constant(ir.IntType(32), 0)
            element_ptr: Optional[ir.Value] = None

            # --- DEFINIÇÃO DAS VARIÁVEIS (GARANTIR QUE ESTEJAM AQUI) ---
            llvm_length: Optional[ir.Value] = None
            is_raw_pointer = False
            collection_is_indexable_with_bounds = False
            # --- FIM DEFINIÇÃO ---

            # Determina llvm_length, is_raw_pointer, etc.
            if isinstance(collection_storage_type, ir.ArrayType):
                llvm_length = ir.Constant(usize_type, collection_storage_type.count)
                collection_is_indexable_with_bounds = True
            elif isinstance(collection_storage_type, (ir.IdentifiedStructType, ir.LiteralStructType)) and \
                 hasattr(collection_storage_type, 'elements') and len(collection_storage_type.elements) == 2 and \
                 isinstance(collection_storage_type.elements[0], ir.PointerType) and \
                 collection_storage_type.elements[1] == usize_type: # Slice
                if not builder or not builder.block or builder.block.is_terminated: self.add_error(...); return None
                len_ptr = builder.gep(llvm_base_collection_ptr, [zero_const_32, ir.Constant(ir.IntType(32), 1)], name="slice.len.ptr.bc")
                llvm_length = builder.load(len_ptr, name="slice.len.bc")
                collection_is_indexable_with_bounds = True
            elif isinstance(collection_storage_type, ir.PointerType):
                 is_raw_pointer = True
                 if not self.is_in_mem_block: self.add_error("Indexação de ponteiro bruto requer bloco 'mem'", node)
            else:
                 self.add_error(f"Tentativa de indexar tipo não suportado: {collection_storage_type}", node.array); return None


            # --- Lógica de Bounds Check e GEP ---
            # Agora as variáveis collection_is_indexable_with_bounds e llvm_length existem
            if collection_is_indexable_with_bounds and llvm_length is not None:
                # --- INSERE CHAMADA PARA HELPER ---
                if not builder or not builder.block or builder.block.is_terminated: self.add_error(...); return None
                check_func = self.module.globals.get("atom_do_bounds_check")
                if not check_func or not isinstance(check_func, ir.Function): self.add_error(...); return None
                builder.call(check_func, [llvm_index_val, llvm_length])
                # --- FIM CHAMADA HELPER ---

                if not builder or not builder.block or builder.block.is_terminated: self.add_error(...); return None
                # Gera o GEP DEPOIS da chamada
                if isinstance(collection_storage_type, ir.ArrayType):
                    element_ptr = builder.gep(llvm_base_collection_ptr, [zero_const_32, llvm_index_val], name="arr.elem.ptr", inbounds=True)
                else: # Slice
                    data_ptr_field_addr = builder.gep(llvm_base_collection_ptr, [zero_const_32, zero_const_32], name="slice.data.ptr.addr", inbounds=True)
                    actual_data_ptr = builder.load(data_ptr_field_addr, name="slice.data.ptr")
                    element_ptr = builder.gep(actual_data_ptr, [llvm_index_val], name="slice.elem.ptr", inbounds=True)

            elif is_raw_pointer:
                 # ... (código GEP para ponteiro bruto como antes) ...
                 if not builder or not builder.block or builder.block.is_terminated: self.add_error(...); return None
                 actual_data_ptr = builder.load(llvm_base_collection_ptr, name="ptr.todata.load")
                 if not isinstance(actual_data_ptr.type, ir.PointerType): self.add_error(...); return None
                 element_ptr = builder.gep(actual_data_ptr, [llvm_index_val], name="ptr.elem.ptr", inbounds=False)
            else:
                 return None

            if element_ptr is None:
                 self.add_error("Erro interno: element_ptr não definido após IndexAccess LValue", node)
                 return None
            return element_ptr

        # --- CASO UNARYOP (DEREF) ---
        elif isinstance(node, ast.UnaryOp) and node.op == '*':
             # ... (código como antes) ...
             llvm_inner_ptr_val = self.visit(node.operand)
             if llvm_inner_ptr_val and isinstance(llvm_inner_ptr_val.type, ir.PointerType):
                  if not self.is_in_mem_block: self.add_error("...", node)
                  return llvm_inner_ptr_val
             else: self.add_error(...); return None
        else:
            self.add_error(f"Expressão do tipo '{type(node).__name__}' não é um L-Value suportado.", node)
            return None

    def define_function_body(self, node: ast.FunctionDef):
        func_name = node.name.name
        llvm_func_val = self.module.globals.get(func_name)
        if not isinstance(llvm_func_val, ir.Function):
            self.add_error(f"Função '{func_name}' não encontrada.", node.name); return
        llvm_func: ir.Function = llvm_func_val
        if llvm_func.blocks and any(b.instructions for b in llvm_func.blocks):
            llvm_func.blocks = [] # Limpa corpo existente se houver

        entry_block = llvm_func.append_basic_block(name="entry")
        old_builder = self.builder
        self.builder = ir.IRBuilder(entry_block)

        old_func_name = self.current_function_name
        self.current_function_name = func_name

        self.enter_scope()
        # Processa parâmetros
        for i, llvm_arg_val in enumerate(llvm_func.args):
            param_node_ast = node.params[i]
            ast_param_name = param_node_ast.name.name
            llvm_arg_val.name = ast_param_name
            alloca_inst = self.builder.alloca(llvm_arg_val.type, name=ast_param_name + ".addr")
            self.builder.store(llvm_arg_val, alloca_inst)
            self.declare_var(ast_param_name, alloca_inst)

        # Processa corpo
        for stmt in node.body:
            self.visit(stmt)
            # PARADA IMPORTANTE: Se um statement (return, break, etc.)
            # terminou o bloco atual, não podemos continuar neste caminho.
            if not self.builder or not self.builder.block or self.builder.block.is_terminated:
                break # Sai do loop de processamento de statements

        self.exit_scope()

        # --- Tratamento do Retorno Implícito / Bloco Final ---
        # Verifica se o último bloco ATUAL do builder está terminado
        current_builder_block_terminated = (not self.builder or not self.builder.block or self.builder.block.is_terminated)

        # Se o builder AINDA está ativo e seu bloco NÃO está terminado
        if not current_builder_block_terminated:
            return_type_llvm = llvm_func.function_type.return_type
            if isinstance(return_type_llvm, ir.VoidType):
                self.builder.ret_void()
            else:
                # Retorna Undef para funções não-void sem retorno explícito
                # Idealmente, a análise semântica pegaria isso, mas evitamos IR inválido.
                undef_val = ir.Constant(return_type_llvm, ir.Undefined)
                self.builder.ret(undef_val)
        # Se todos os caminhos terminaram com 'ret' ou similar, não fazemos nada aqui.
        # Verifica se a função ficou completamente vazia (sem blocos)
        elif not llvm_func.blocks:
             # Recria o builder no entry block (que deveria existir)
             self.builder = ir.IRBuilder(entry_block)
             return_type_llvm = llvm_func.function_type.return_type
             if isinstance(return_type_llvm, ir.VoidType): self.builder.ret_void()
             else: self.builder.ret(ir.Constant(return_type_llvm, ir.Undefined))

        self.builder = old_builder
        self.current_function_name = old_func_name

    def visit(self, node: Optional[ast.Node], expected_llvm_type: Optional[ir.Type] = None):
        if node is None: return None
        method_name = f'visit_{node.__class__.__name__}'
        visitor_method = getattr(self, method_name, self.generic_visit)
        import inspect
        sig = inspect.signature(visitor_method)
        try:
            if 'expected_llvm_type' in sig.parameters:
                 return visitor_method(node, expected_llvm_type=expected_llvm_type)
            else:
                 # Avisa se estamos passando expected_type para um método que não o aceita
                 # if expected_llvm_type is not None and method_name != 'generic_visit':
                 #    print(f"WARN: Passando expected_llvm_type para {method_name} que não o aceita.")
                 return visitor_method(node)
        except Exception as e:
            self.add_error(f"Erro interno ao visitar nó {type(node).__name__} com método {method_name}: {e}", node)
            traceback.print_exc() # Imprime traceback para debug
            return None # Retorna None para indicar falha na geração

    def generic_visit(self, node: ast.Node):
        self.add_error(f"Geração de código não implementada para o nó AST: {type(node).__name__}", node)
        return None

    # --- Statement Visitors ---
    def visit_LetBinding(self, node: ast.LetBinding):
        # ... (código como antes) ...
        var_name = node.name.name
        if not self.builder or (self.builder.block and self.builder.block.is_terminated):
            self.add_error(f"Builder inativo/terminado para LetBinding '{var_name}'.", node); return
        expected_llvm_type: Optional[ir.Type] = None
        if node.type_annot: expected_llvm_type = self.get_llvm_type(node.type_annot)
        if expected_llvm_type is None and hasattr(node, 'declared_type'): # Tenta pegar do semantic analyzer
             expected_llvm_type = self.get_llvm_type(node.declared_type)
        if expected_llvm_type is None and not node.type_annot: # Ainda None, tenta inferir do RHS
             pass # Deixa para inferir do valor RHS
        elif expected_llvm_type is None: # Falha ao obter tipo anotado
             self.add_error(f"Falha tipo anotado LLVM 'let {var_name}'.", node.type_annot); return

        llvm_rhs_value = self.visit(node.value, expected_llvm_type=expected_llvm_type)
        if llvm_rhs_value is None: self.add_error(f"Falha valor RHS 'let {var_name}'.", node.value); return
        llvm_var_type: Optional[ir.Type] = expected_llvm_type or llvm_rhs_value.type
        if llvm_var_type is None: self.add_error(f"Falha tipo final 'let {var_name}'.", node); return

        llvm_value_to_store = llvm_rhs_value
        if llvm_rhs_value.type != llvm_var_type: # Cast/Coerção
            # ... (lógica de cast/coerção como antes, incluindo array->slice) ...
            if isinstance(llvm_rhs_value.type, ir.IntType) and isinstance(llvm_var_type, ir.IntType):
                 is_signed_heuristic = self.is_signed_type_heuristic(getattr(node.value, 'atom_type', None), llvm_rhs_value.type)
                 if llvm_var_type.width > llvm_rhs_value.type.width: llvm_value_to_store = self.builder.sext(llvm_rhs_value, llvm_var_type) if is_signed_heuristic else self.builder.zext(llvm_rhs_value, llvm_var_type)
                 elif llvm_var_type.width < llvm_rhs_value.type.width: llvm_value_to_store = self.builder.trunc(llvm_rhs_value, llvm_var_type)
                 else: llvm_value_to_store = self.builder.bitcast(llvm_rhs_value, llvm_var_type)
            elif isinstance(llvm_rhs_value.type, ir.PointerType) and isinstance(llvm_var_type, ir.PointerType):
                 llvm_value_to_store = self.builder.bitcast(llvm_rhs_value, llvm_var_type)
            elif isinstance(llvm_rhs_value.type, ir.PointerType) and \
                 isinstance(llvm_rhs_value.type.pointee, ir.ArrayType) and \
                 isinstance(llvm_var_type, (ir.LiteralStructType, ir.IdentifiedStructType)) and \
                 hasattr(llvm_var_type, 'elements') and len(llvm_var_type.elements) == 2 and \
                 isinstance(llvm_var_type.elements[0], ir.PointerType) and \
                 llvm_var_type.elements[1] == self.llvm_types['usize'] and \
                 llvm_var_type.elements[0].pointee == llvm_rhs_value.type.pointee.element:
                array_ptr_val = llvm_rhs_value
                array_type_llvm = llvm_rhs_value.type.pointee
                slice_element_ptr_type_llvm = llvm_var_type.elements[0]
                zero_idx = ir.Constant(ir.IntType(32), 0)
                ptr_to_first_elem = self.builder.gep(array_ptr_val, [zero_idx, zero_idx], name="arraydecay.ptr")
                if ptr_to_first_elem.type != slice_element_ptr_type_llvm:
                    ptr_to_first_elem = self.builder.bitcast(ptr_to_first_elem, slice_element_ptr_type_llvm)
                array_len = array_type_llvm.count
                len_val_const = ir.Constant(self.llvm_types['usize'], array_len)
                undef_slice_struct = ir.Constant(llvm_var_type, None)
                slice_with_ptr = self.builder.insert_value(undef_slice_struct, ptr_to_first_elem, 0)
                llvm_value_to_store = self.builder.insert_value(slice_with_ptr, len_val_const, 1, name=var_name + ".sliceval")
                #print(f"  DEBUG Let/Mut/Assign '{var_name}': Coerção de &array para slice: {llvm_value_to_store}")
            else: self.add_error(f"Tipo RHS incompatível 'let {var_name}'.", node); return

        llvm_ptr = self.builder.alloca(llvm_var_type, name=var_name + ".addr")
        try: self.builder.store(llvm_value_to_store, llvm_ptr)
        except Exception as e: self.add_error(f"Store falhou 'let {var_name}': {e}", node); return
        self.declare_var(var_name, llvm_ptr)


    def visit_MutBinding(self, node: ast.MutBinding):
        # ... (código similar a LetBinding) ...
        var_name = node.name.name
        if not self.builder or (self.builder.block and self.builder.block.is_terminated):
            self.add_error(f"Builder inativo/terminado para MutBinding '{var_name}'.", node); return
        expected_llvm_type: Optional[ir.Type] = None
        if node.type_annot: expected_llvm_type = self.get_llvm_type(node.type_annot)
        if expected_llvm_type is None and hasattr(node, 'declared_type'):
             expected_llvm_type = self.get_llvm_type(node.declared_type)
        if expected_llvm_type is None and not node.type_annot: pass
        elif expected_llvm_type is None: self.add_error(f"Falha tipo anotado LLVM 'mut {var_name}'.", node.type_annot); return

        llvm_rhs_value = self.visit(node.value, expected_llvm_type=expected_llvm_type)
        if llvm_rhs_value is None: self.add_error(f"Falha valor RHS 'mut {var_name}'.", node.value); return
        llvm_var_type: Optional[ir.Type] = expected_llvm_type or llvm_rhs_value.type
        if llvm_var_type is None: self.add_error(f"Falha tipo final 'mut {var_name}'.", node); return

        llvm_value_to_store = llvm_rhs_value
        if llvm_rhs_value.type != llvm_var_type: # Cast/Coerção
            # ... (lógica de cast/coerção como antes, incluindo array->slice) ...
            if isinstance(llvm_rhs_value.type, ir.IntType) and isinstance(llvm_var_type, ir.IntType):
                 is_signed_heuristic = self.is_signed_type_heuristic(getattr(node.value, 'atom_type', None), llvm_rhs_value.type)
                 if llvm_var_type.width > llvm_rhs_value.type.width: llvm_value_to_store = self.builder.sext(llvm_rhs_value, llvm_var_type) if is_signed_heuristic else self.builder.zext(llvm_rhs_value, llvm_var_type)
                 elif llvm_var_type.width < llvm_rhs_value.type.width: llvm_value_to_store = self.builder.trunc(llvm_rhs_value, llvm_var_type)
                 else: llvm_value_to_store = self.builder.bitcast(llvm_rhs_value, llvm_var_type)
            elif isinstance(llvm_rhs_value.type, ir.PointerType) and isinstance(llvm_var_type, ir.PointerType):
                 llvm_value_to_store = self.builder.bitcast(llvm_rhs_value, llvm_var_type)
            elif isinstance(llvm_rhs_value.type, ir.PointerType) and \
                 isinstance(llvm_rhs_value.type.pointee, ir.ArrayType) and \
                 isinstance(llvm_var_type, (ir.LiteralStructType, ir.IdentifiedStructType)) and \
                 hasattr(llvm_var_type, 'elements') and len(llvm_var_type.elements) == 2 and \
                 isinstance(llvm_var_type.elements[0], ir.PointerType) and \
                 llvm_var_type.elements[1] == self.llvm_types['usize'] and \
                 llvm_var_type.elements[0].pointee == llvm_rhs_value.type.pointee.element:
                array_ptr_val = llvm_rhs_value
                array_type_llvm = llvm_rhs_value.type.pointee
                slice_element_ptr_type_llvm = llvm_var_type.elements[0]
                zero_idx = ir.Constant(ir.IntType(32), 0)
                ptr_to_first_elem = self.builder.gep(array_ptr_val, [zero_idx, zero_idx], name="arraydecay.ptr")
                if ptr_to_first_elem.type != slice_element_ptr_type_llvm:
                    ptr_to_first_elem = self.builder.bitcast(ptr_to_first_elem, slice_element_ptr_type_llvm)
                array_len = array_type_llvm.count
                len_val_const = ir.Constant(self.llvm_types['usize'], array_len)
                undef_slice_struct = ir.Constant(llvm_var_type, None)
                slice_with_ptr = self.builder.insert_value(undef_slice_struct, ptr_to_first_elem, 0)
                llvm_value_to_store = self.builder.insert_value(slice_with_ptr, len_val_const, 1, name=var_name + ".sliceval")
                #print(f"  DEBUG Let/Mut/Assign '{var_name}': Coerção de &array para slice: {llvm_value_to_store}")
            else: self.add_error(f"Tipo RHS incompatível 'mut {var_name}'.", node); return

        llvm_ptr = self.builder.alloca(llvm_var_type, name=var_name + ".addr")
        try: self.builder.store(llvm_value_to_store, llvm_ptr)
        except Exception as e: self.add_error(f"Store falhou 'mut {var_name}': {e}", node); return
        self.declare_var(var_name, llvm_ptr)

    def visit_Assignment(self, node: ast.Assignment):
        # ... (código como antes, mas usa visit_lvalue_pointer) ...
        if not self.builder or (self.builder.block and self.builder.block.is_terminated):
             self.add_error("Builder inativo/terminado para Assignment.", node); return
        llvm_target_ptr = self.visit_lvalue_pointer(node.target) # visit_lvalue_pointer já faz bounds check
        if llvm_target_ptr is None: self.add_error(f"Falha L-Value Assignment.", node.target); return
        if not isinstance(llvm_target_ptr.type, ir.PointerType): self.add_error(f"L-Value não é ponteiro.", node.target); return

        expected_value_type = llvm_target_ptr.type.pointee
        llvm_value = self.visit(node.value, expected_llvm_type=expected_value_type)
        if llvm_value is None: self.add_error(f"Falha valor RHS Assignment.", node.value); return

        value_to_store = llvm_value
        if llvm_value.type != expected_value_type: # Cast/Coerção
            # ... (lógica de cast/coerção como antes, incluindo slice->slice) ...
            if isinstance(llvm_value.type, ir.IntType) and isinstance(expected_value_type, ir.IntType):
                 is_signed_heuristic = self.is_signed_type_heuristic(getattr(node.value, 'atom_type', None), llvm_value.type)
                 if expected_value_type.width > llvm_value.type.width: value_to_store = self.builder.sext(llvm_value, expected_value_type) if is_signed_heuristic else self.builder.zext(llvm_value, expected_value_type)
                 elif expected_value_type.width < llvm_value.type.width: value_to_store = self.builder.trunc(llvm_value, expected_value_type)
                 else: value_to_store = self.builder.bitcast(llvm_value, expected_value_type)
            elif isinstance(llvm_value.type, ir.PointerType) and isinstance(expected_value_type, ir.PointerType):
                 value_to_store = self.builder.bitcast(llvm_value, expected_value_type)
            elif isinstance(llvm_value.type, (ir.LiteralStructType, ir.IdentifiedStructType)) and \
                 isinstance(expected_value_type, (ir.LiteralStructType, ir.IdentifiedStructType)) and \
                 hasattr(expected_value_type, 'name') and hasattr(expected_value_type, 'elements') and len(expected_value_type.elements) == 2 and \
                 hasattr(llvm_value.type, 'elements') and len(llvm_value.type.elements) == 2: # Slice assignment
                 ptr_field_rhs = self.builder.extract_value(llvm_value, 0)
                 len_field_rhs = self.builder.extract_value(llvm_value, 1)
                 casted_ptr_field = ptr_field_rhs
                 if ptr_field_rhs.type != expected_value_type.elements[0]:
                     casted_ptr_field = self.builder.bitcast(ptr_field_rhs, expected_value_type.elements[0])
                 temp_agg = ir.Constant(expected_value_type, None) # Undef
                 temp_agg = self.builder.insert_value(temp_agg, casted_ptr_field, 0)
                 value_to_store = self.builder.insert_value(temp_agg, len_field_rhs, 1)
            else: self.add_error(f"Tipos incompatíveis Assignment.", node); return

        try: self.builder.store(value_to_store, llvm_target_ptr)
        except Exception as e: self.add_error(f"Store falhou Assignment: {e}", node)

          
    def visit_ExpressionStatement(self, node: ast.ExpressionStatement):
         if not self.builder or (self.builder.block and self.builder.block.is_terminated): return
         # Apenas visita a expressão, ignora o resultado. NENHUM LOAD extra aqui.
         self.visit(node.expression)

    

    def visit_ReturnStmt(self, node: ast.ReturnStmt):
        # ... (código como antes) ...
        if not self.builder or (self.builder.block and self.builder.block.is_terminated): return
        expected_ret_type_llvm = None
        if self.builder and self.builder.function: expected_ret_type_llvm = self.builder.function.function_type.return_type
        if node.value:
            llvm_value = self.visit(node.value, expected_llvm_type=expected_ret_type_llvm)
            if llvm_value is None: self.add_error(...); return
            if expected_ret_type_llvm and llvm_value.type != expected_ret_type_llvm: # Cast
                casted_value = None # ... (lógica de cast) ...
                if isinstance(llvm_value.type, ir.IntType) and isinstance(expected_ret_type_llvm, ir.IntType):
                    is_signed = self.is_signed_type_heuristic(getattr(node.value,'atom_type',None), llvm_value.type)
                    if expected_ret_type_llvm.width > llvm_value.type.width: casted_value = self.builder.sext(llvm_value, expected_ret_type_llvm) if is_signed else self.builder.zext(llvm_value, expected_ret_type_llvm)
                    elif expected_ret_type_llvm.width < llvm_value.type.width: casted_value = self.builder.trunc(llvm_value, expected_ret_type_llvm)
                    else: casted_value = self.builder.bitcast(llvm_value, expected_ret_type_llvm)
                elif isinstance(llvm_value.type, ir.PointerType) and isinstance(expected_ret_type_llvm, ir.PointerType):
                    casted_value = self.builder.bitcast(llvm_value, expected_ret_type_llvm)
                if casted_value: llvm_value = casted_value
                else: self.add_error(...); return
            self.builder.ret(llvm_value)
        else: # return; (void)
            if expected_ret_type_llvm and not isinstance(expected_ret_type_llvm, ir.VoidType): self.add_error(...)
            self.builder.ret_void()

    def visit_IfStmt(self, node: ast.IfStmt):
        if not self.builder or not self.builder.block or self.builder.block.is_terminated:
            # Se o builder já está inativo antes do if, não faz nada
            return

        current_function = self.builder.function
        bool_type_llvm = self.llvm_types.get('bool')
        if not bool_type_llvm: self.add_error("FATAL: Tipo bool não definido.", node); return

        # Avalia condição
        cond_val = self.visit(node.condition, expected_llvm_type=bool_type_llvm)
        if cond_val is None: self.add_error("Falha ao gerar condição do IfStmt.", node.condition); return

        # Converte condição para bool (i1) se necessário
        if cond_val.type != bool_type_llvm:
            if isinstance(cond_val.type, ir.IntType):
                zero = ir.Constant(cond_val.type, 0)
                cond_val = self.builder.icmp_unsigned('!=', cond_val, zero, name="ifcond.tobool")
            else:
                self.add_error(f"Condição IfStmt ({cond_val.type}) não pode ser bool.", node.condition); return

        # Cria blocos
        then_block = current_function.append_basic_block(name="if.then")
        else_block_present = node.else_block is not None
        else_block_actual: Optional[ir.Block] = None
        merge_block: Optional[ir.Block] = None # Será criado se necessário

        if else_block_present:
            else_block_actual = current_function.append_basic_block(name="if.else")
            # Se há else, o merge block só é criado se PELO MENOS UM dos ramos (then ou else) continuar
        else:
            # Se não há else, o merge block é o destino do 'false' e só é útil se 'then' continuar
            merge_block = current_function.append_basic_block(name="if.end")

        # Bloco de destino para o branch 'false' da condição
        false_target_block = else_block_actual if else_block_actual else merge_block
        if false_target_block is None: # Defesa: não deveria acontecer com a lógica acima
             self.add_error("Erro interno: Bloco de destino falso do if não determinado.", node); return

        # Branch condicional inicial
        self.builder.cbranch(cond_val, then_block, false_target_block)

        # --- Bloco THEN ---
        self.builder.position_at_end(then_block)
        then_path_continues = True # Assume que continua
        for stmt in node.then_block:
            self.visit(stmt)
            if not self.builder or not self.builder.block or self.builder.block.is_terminated:
                then_path_continues = False; break # Caminho terminou
        # Se o then continuou, precisa saltar para o merge
        if then_path_continues:
            if merge_block is None: # Cria merge se ainda não existe (caso onde havia 'else')
                 merge_block = current_function.append_basic_block(name="if.end")
            self.builder.branch(merge_block)

        # --- Bloco ELSE ---
        else_path_continues = True # Assume que continua
        if else_block_actual:
            self.builder.position_at_end(else_block_actual)
            if isinstance(node.else_block, ast.IfStmt): # Else If
                self.visit(node.else_block)
                # Verifica se o builder terminou DENTRO do 'else if'
                if not self.builder or not self.builder.block or self.builder.block.is_terminated:
                    else_path_continues = False
            elif isinstance(node.else_block, list): # Else { ... }
                 for stmt in node.else_block:
                      self.visit(stmt)
                      if not self.builder or not self.builder.block or self.builder.block.is_terminated:
                           else_path_continues = False; break # Caminho terminou
            # Se o else continuou, precisa saltar para o merge
            if else_path_continues:
                if merge_block is None: # Cria merge se ainda não existe
                     merge_block = current_function.append_basic_block(name="if.end")
                # Garante que o builder está posicionado corretamente antes do branch
                if self.builder and self.builder.block and not self.builder.block.is_terminated:
                     self.builder.branch(merge_block)

        # --- Posiciona no Bloco MERGE (se ele foi criado e é potencialmente alcançável) ---
        if merge_block is not None:
             # Verifica se o merge_block tem predecessores (senão, é inalcançável)
             # Ou se algum dos branches (then/else) continuou
             if then_path_continues or else_path_continues:
                  self.builder.position_at_end(merge_block)
             else:
                  # Se ambos os caminhos terminaram, o merge é inalcançável.
                  # Deixa o builder onde o último caminho terminou (provavelmente None ou terminado).
                  # Se o bloco existir mas for inalcançável, o LLVM pode otimizá-lo.
                  pass
        # Se merge_block não foi criado, significa que ambos then/else (se existia) terminaram.
        # O builder já está posicionado corretamente (provavelmente None ou terminado).

    def visit_WhileStmt(self, node: ast.WhileStmt):
        if not self.builder or not self.builder.block or self.builder.block.is_terminated: return

        current_function = self.builder.function
        cond_block = current_function.append_basic_block(name="while.cond")
        body_block = current_function.append_basic_block(name="while.body")
        end_block = current_function.append_basic_block(name="while.end")

        self.builder.branch(cond_block)

        # --- Bloco de Condição ---
        self.builder.position_at_end(cond_block)
        bool_type_llvm = self.llvm_types.get('bool') # ... (check bool_type) ...
        cond_val = self.visit(node.condition, expected_llvm_type=bool_type_llvm)
        # ... (check cond_val, convert to bool) ...
        if cond_val is None: self.add_error(...); self.builder.branch(end_block); self.builder.position_at_end(end_block); return
        if cond_val.type != bool_type_llvm:
            if isinstance(cond_val.type, ir.IntType): cond_val = self.builder.icmp_unsigned('!=', cond_val, ir.Constant(cond_val.type, 0))
            else: self.add_error(...); self.builder.branch(end_block); self.builder.position_at_end(end_block); return
        self.builder.cbranch(cond_val, body_block, end_block)

        # --- Bloco do Corpo ---
        self.loop_context_stack.append((cond_block, end_block))
        self.builder.position_at_end(body_block)
        # Salva o bloco inicial do corpo para checagem posterior
        entry_body_block = body_block

        for stmt in node.body:
            # Verifica se o builder está ok ANTES de visitar o statement
            if not self.builder or not self.builder.block or self.builder.block.is_terminated:
                break # Sai se um statement anterior terminou o bloco

            current_block_before_visit = self.builder.block # Bloco atual
            self.visit(stmt)

            # Verifica se o statement visitado terminou o bloco atual
            if not self.builder or not self.builder.block or self.builder.block.is_terminated:
                 break # Sai do loop for

            # Se o statement foi um break/continue, o builder já foi reposicionado.
            # Se não foi, o builder ainda deve estar no mesmo bloco (ou um sub-bloco de if/else)
            # Se o builder ainda está ativo e não terminou, significa que este statement
            # não causou um break/continue/return que terminou o fluxo.

        self.loop_context_stack.pop()

        # --- Salto Final do Corpo ---
        # Verifica se o builder está ativo e em um bloco que NÃO seja o end_block
        # e que não esteja terminado. Isso significa que a execução chegou ao fim
        # do corpo do loop sem um break/return.
        if self.builder and self.builder.block and \
           self.builder.block != end_block and \
           not self.builder.block.is_terminated:
            self.builder.branch(cond_block) # Salta de volta para a condição

        # Posiciona no bloco final (destino do break ou da condição falsa)
        self.builder.position_at_end(end_block)
        # Garante que end_block tenha um predecessor válido se ficou órfão
        # (Isso é complexo, o LLVM pode lidar com isso, mas pode ser fonte de erros)
        # if not end_block.predecessors:
        #    # Se o loop nunca puder sair (sem break e condição sempre true),
        #    # este bloco é inalcançável. Poderíamos removê-lo ou adicionar unreachable?
        #    # Por segurança, vamos deixar como está por enquanto.
        #    pass


    def visit_LoopStmt(self, node: ast.LoopStmt):
        if not self.builder or not self.builder.block or self.builder.block.is_terminated:
            return

        current_function = self.builder.function
        loop_header_block = current_function.append_basic_block(name="loop.header")
        loop_end_block = current_function.append_basic_block(name="loop.end") # Alvo do break

        # Salto inicial para o header/corpo
        self.builder.branch(loop_header_block)

        # --- Bloco Header/Corpo ---
        self.builder.position_at_end(loop_header_block)
        self.loop_context_stack.append((loop_header_block, loop_end_block)) # Header é alvo do continue

        # Processa statements do corpo
        for stmt in node.body:
             self.visit(stmt)
             # Se um statement terminou o bloco (ret, break, continue)
             if not self.builder or not self.builder.block or self.builder.block.is_terminated:
                  break # Para de processar statements neste caminho

        self.loop_context_stack.pop()

        # --- Salto de volta para o Header ---
        # APÓS processar TODOS os statements do loop, verifica se o builder
        # ainda está ativo e em um bloco que NÃO seja o loop_end_block
        # (se for o loop_end_block, significa que o último statement foi um break)
        # e se o bloco atual NÃO está terminado por um return ou outro break/continue
        # direcionado para fora do loop.
        if self.builder and self.builder.block and \
           self.builder.block != loop_end_block and \
           not self.builder.block.is_terminated:
            # Se o fluxo chegou ao final do corpo sem break/ret/continue, salta de volta
            self.builder.branch(loop_header_block)

        # Posiciona o builder no bloco final após o loop (destino do break)
        # Se o loop nunca termina (sem break), este bloco pode ficar órfão,
        # mas é necessário como destino do break.
        self.builder.position_at_end(loop_end_block)

    def visit_BreakStmt(self, node: ast.BreakStmt):
        # ... (código como antes) ...
        if not self.builder or (self.builder.block and self.builder.block.is_terminated): return
        if not self.loop_context_stack: self.add_error(...); return
        _, break_target = self.loop_context_stack[-1]
        self.builder.branch(break_target)

    def visit_ContinueStmt(self, node: ast.ContinueStmt):
        # ... (código como antes) ...
        if not self.builder or (self.builder.block and self.builder.block.is_terminated): return
        if not self.loop_context_stack: self.add_error(...); return
        continue_target, _ = self.loop_context_stack[-1]
        self.builder.branch(continue_target)

    def visit_MemBlock(self, node: ast.MemBlock): # Sem mudança aqui
        if not self.builder or not self.builder.block or self.builder.block.is_terminated:
            return 

        # A flag is_in_mem_block é da análise semântica, não necessária no codegen.
        # Apenas visita os statements internos.
        for stmt in node.body:
            self.visit(stmt)
            if not self.builder or not self.builder.block or self.builder.block.is_terminated:
                break
                
    def visit_EMemBlock(self, node: ast.EMemBlock): # <--- NOVO MÉTODO
        # A lógica de geração de código para e_mem é idêntica à de mem.
        # A diferença de escopo foi tratada na análise semântica.
        # O CodeGen apenas precisa gerar o código para os statements internos.
        if not self.builder or not self.builder.block or self.builder.block.is_terminated:
            return

        # Visita os statements internos.
        for stmt in node.body:
            self.visit(stmt)
            if not self.builder or not self.builder.block or self.builder.block.is_terminated:
                break

    # --- Expression Visitors ---
          
          
    def visit_Identifier(self, node: ast.Identifier, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
        var_name = node.name

        # 1. Verifica se é uma função global conhecida (PRIORIDADE)
        llvm_global_func = self.module.globals.get(var_name)
        if isinstance(llvm_global_func, ir.Function):
            # --- DEBUG ---
            # if var_name == 'printf': print(f"DEBUG visit_Identifier: Found '{var_name}' as global Function via module.globals.")
            # --- FIM DEBUG ---
            return llvm_global_func # Retorna a função diretamente

        # 2. Verifica se está na tabela de símbolos local/param
        llvm_symbol = self.lookup_var(var_name)
        if llvm_symbol is not None:
            # Verifica se, por acaso, o lookup retornou a função global (deveria ser o mesmo objeto)
            if isinstance(llvm_symbol, ir.Function):
                 # if var_name == 'printf': print(f"DEBUG visit_Identifier: Found '{var_name}' as Function via lookup_var.")
                 return llvm_symbol

            # Se não é função, DEVE ser um ponteiro (alloca)
            if isinstance(llvm_symbol.type, ir.PointerType):
                if not self.builder:
                    self.add_error(f"Builder inativo ao carregar var local/param '{var_name}'", node)
                    return None
                # --- DEBUG ---
                # if var_name == 'printf': print(f"  DEBUG visit_Identifier: '{var_name}' ENCONTRADO COMO PONTEIRO LOCAL?? Type: {llvm_symbol.type}. Loading...") # Erro!
                # --- FIM DEBUG ---
                loaded_val = self.builder.load(llvm_symbol, name=var_name)
                # ... (Cast opcional do valor carregado) ...
                if expected_llvm_type and loaded_val.type != expected_llvm_type:
                    if isinstance(loaded_val.type, ir.IntType) and isinstance(expected_llvm_type, ir.IntType):
                        if expected_llvm_type.width > loaded_val.type.width: loaded_val = self.builder.zext(loaded_val, expected_llvm_type)
                        elif expected_llvm_type.width < loaded_val.type.width: loaded_val = self.builder.trunc(loaded_val, expected_llvm_type)
                    elif isinstance(loaded_val.type, ir.PointerType) and isinstance(expected_llvm_type, ir.PointerType):
                        loaded_val = self.builder.bitcast(loaded_val, expected_llvm_type)
                return loaded_val
            else:
                self.add_error(f"Símbolo local/param inesperado '{var_name}' (não é ponteiro nem função): {type(llvm_symbol)}.", node)
                return None

        # 3. Verifica se é uma constante global (não encontrada antes)
        # Nota: llvm_global_func já foi verificado acima
        llvm_global_const = self.module.globals.get(var_name) # Pega de novo caso lookup_var não tenha pego
        if isinstance(llvm_global_const, ir.GlobalVariable) and llvm_global_const.global_constant:
            if llvm_global_const.initializer is None:
                self.add_error(f"Constante global '{var_name}' usada mas não inicializada.", node)
                return ir.Constant(llvm_global_const.type.pointee, ir.Undefined)
            const_val = llvm_global_const.initializer
            # ... (Cast opcional da constante) ...
            if expected_llvm_type and const_val.type != expected_llvm_type and self.builder:
                 if isinstance(const_val.type, ir.IntType) and isinstance(expected_llvm_type, ir.IntType):
                    if expected_llvm_type.width > const_val.type.width: const_val = self.builder.zext(const_val, expected_llvm_type)
                    elif expected_llvm_type.width < const_val.type.width: const_val = self.builder.trunc(const_val, expected_llvm_type)
                    else: const_val = self.builder.bitcast(const_val, expected_llvm_type)
                 elif isinstance(const_val.type, ir.PointerType) and isinstance(expected_llvm_type, ir.PointerType):
                     const_val = self.builder.bitcast(const_val, expected_llvm_type)
            return const_val

        # 4. Se não encontrou em lugar nenhum
        self.add_error(f"Identificador '{var_name}' não definido.", node)
        return None      


    def visit_UnaryOp(self, node: ast.UnaryOp, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
        # ... (código como antes) ...
        op = node.op
        if op == '&' or op == '&mut':
            if isinstance(node.operand, ast.ArrayLiteral) and not node.operand.elements: # &[] ou &mut []
                # ... (lógica para slice vazio) ...
                target_slice_type: Optional[ir.Type] = None; ptr_elem_type_for_null = ir.IntType(8)
                if isinstance(expected_llvm_type, (ir.LiteralStructType, ir.IdentifiedStructType)) and \
                   hasattr(expected_llvm_type, 'elements') and len(expected_llvm_type.elements) == 2 and \
                   isinstance(expected_llvm_type.elements[0], ir.PointerType) and \
                   expected_llvm_type.elements[1] == self.llvm_types['usize']:
                    target_slice_type = expected_llvm_type; ptr_elem_type_for_null = expected_llvm_type.elements[0].pointee
                else: ptr_type = ir.PointerType(ptr_elem_type_for_null); len_type = self.llvm_types['usize']; target_slice_type = ir.LiteralStructType([ptr_type, len_type]); # Default
                null_ptr = ir.Constant(ir.PointerType(ptr_elem_type_for_null), None)
                zero_len = ir.Constant(self.llvm_types['usize'], 0)
                if isinstance(target_slice_type, ir.IdentifiedStructType) and self.builder:
                    undef_slice = ir.Constant(target_slice_type, None); slice_val_ptr = self.builder.insert_value(undef_slice, null_ptr, 0); return self.builder.insert_value(slice_val_ptr, zero_len, 1)
                elif isinstance(target_slice_type, ir.LiteralStructType): return ir.Constant(target_slice_type, [null_ptr, zero_len])
                else: self.add_error(...); return None
            else: # &LValue ou &mut LValue
                llvm_lvalue_ptr = self.visit_lvalue_pointer(node.operand)
                if llvm_lvalue_ptr:
                    if isinstance(expected_llvm_type, ir.PointerType) and llvm_lvalue_ptr.type != expected_llvm_type and self.builder:
                         return self.builder.bitcast(llvm_lvalue_ptr, expected_llvm_type)
                    return llvm_lvalue_ptr
                else: self.add_error(...); return None
        llvm_operand_value = self.visit(node.operand) # Não passa expected_type para operando de -, !, *, ~
        if llvm_operand_value is None: return None
        if not self.builder: self.add_error(...); return None
        llvm_operand_type = llvm_operand_value.type
        if op == '-':
             if isinstance(llvm_operand_type, ir.IntType): return self.builder.neg(llvm_operand_value)
             #elif isinstance(llvm_operand_type, (ir.FloatType, ir.DoubleType)): return self.builder.fneg(llvm_operand_value) # REMOVIDO FLOAT
             else: self.add_error(...); return None
        elif op == '!':
             bool_type = self.llvm_types.get('bool')
             if llvm_operand_type == bool_type: return self.builder.not_(llvm_operand_value) # Use not_
             else: self.add_error(...); return None
        elif op == '*':
             if isinstance(llvm_operand_type, ir.PointerType): return self.builder.load(llvm_operand_value)
             else: self.add_error(...); return None
        elif op == '~':
             if isinstance(llvm_operand_type, ir.IntType): return self.builder.not_(llvm_operand_value) # Use not_
             else: self.add_error(...); return None
        else: self.add_error(...); return None


    def visit_BinaryOp(self, node: ast.BinaryOp, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
        op = node.op
        if op == '&&' or op == '||': return self._generate_logical_binary_op(node)
        if not self.builder: self.add_error("Builder inativo", node); return None

        # --- CORREÇÃO: Visita operandos SEM passar expected_llvm_type de comparação ---
        llvm_left = self.visit(node.left) # Não passa expected_llvm_type
        if llvm_left is None: return None
        llvm_right = self.visit(node.right) # Não passa expected_llvm_type
        if llvm_right is None: return None
        # --- FIM CORREÇÃO ---

        left_llvm_type = llvm_left.type
        right_llvm_type = llvm_right.type

        # --- Lógica de Promoção/Ajuste de Tipo (como antes, mas agora com tipos corretos) ---
        final_op_type = left_llvm_type # Tipo padrão do resultado (antes da comparação)
        if self.is_integer_type(left_llvm_type) and self.is_integer_type(right_llvm_type):
            if left_llvm_type != right_llvm_type:
                # Ajusta RHS para tipo LHS para operações aritméticas/bitwise
                # Para comparação, LLVM pode lidar com tipos diferentes, mas vamos manter o ajuste por consistência
                target_type = left_llvm_type
                is_rhs_signed = self.is_signed_type_heuristic(getattr(node.right, 'atom_type', None), right_llvm_type)
                if target_type.width < right_llvm_type.width: llvm_right = self.builder.trunc(llvm_right, target_type)
                elif target_type.width > right_llvm_type.width: llvm_right = self.builder.sext(llvm_right, target_type) if is_rhs_signed else self.builder.zext(llvm_right, target_type)
                else: llvm_right = self.builder.bitcast(llvm_right, target_type) # Caso raro mesmo tamanho, tipo diferente
            final_op_type = left_llvm_type
        elif isinstance(left_llvm_type, ir.PointerType) and isinstance(right_llvm_type, ir.PointerType):
            pass # Ok para comparação
        elif left_llvm_type != right_llvm_type and op not in ('==', '!=', '<', '>', '<=', '>='):
             # Erro apenas se não for comparação e tipos forem diferentes (após ajuste int)
             self.add_error(f"Tipos incompatíveis para op '{op}': {left_llvm_type} vs {right_llvm_type}", node); return None


        # --- Geração da Instrução ---
        if op in ('+', '-', '*', '/', '%'):
             # ... (lógica aritmética, DEVE usar llvm_left, llvm_right ajustados) ...
             if isinstance(final_op_type, ir.IntType): # Usa final_op_type ajustado
                if op == '+': return self.builder.add(llvm_left, llvm_right, name="addtmp")
                if op == '-': return self.builder.sub(llvm_left, llvm_right, name="subtmp")
                if op == '*': return self.builder.mul(llvm_left, llvm_right, name="multmp")
                is_signed = self.is_signed_type_heuristic(getattr(node.left, 'atom_type', None), final_op_type)
                if op == '/': return self.builder.sdiv(llvm_left, llvm_right) if is_signed else self.builder.udiv(llvm_left, llvm_right)
                else: return self.builder.srem(llvm_left, llvm_right) if is_signed else self.builder.urem(llvm_left, llvm_right)
             else: self.add_error(...); return None
        elif op in ('==', '!=', '<', '>', '<=', '>='):
             # --- CORREÇÃO: Usa llvm_left e llvm_right ORIGINAIS para icmp ---
             # LLVM icmp pode comparar inteiros de larguras diferentes (geralmente promovendo)
             # ou ponteiros. A promoção/ajuste que fizemos acima pode não ser ideal aqui.
             # Vamos comparar os valores como foram gerados originalmente.
             original_left_val = self.visit(node.left) # Visita de novo? Não, usa os já visitados.
             original_right_val = self.visit(node.right)
             # Precisamos re-visitar ou guardar os valores originais? Vamos usar os que temos (llvm_left, llvm_right)
             # mas garantir que a comparação use os tipos corretos.

             # Usa os tipos originais detectados para determinar signed/unsigned/ptr
             left_concrete_orig = self.get_concrete_type(getattr(node.left, 'atom_type', left_llvm_type))
             right_concrete_orig = self.get_concrete_type(getattr(node.right, 'atom_type', right_llvm_type))

             if isinstance(left_concrete_orig, ir.PointerType) and isinstance(right_concrete_orig, ir.PointerType):
                  return self.builder.icmp_unsigned(op, llvm_left, llvm_right, name="ptrcmp")
             elif self.is_integer_type(left_concrete_orig) and self.is_integer_type(right_concrete_orig):
                  # Usa a heurística baseada no tipo Atom do operando esquerdo para signed/unsigned
                  is_signed = self.is_signed_type_heuristic(getattr(node.left, 'atom_type', None), left_concrete_orig)
                  if is_signed:
                       return self.builder.icmp_signed(op, llvm_left, llvm_right, name="scmp")
                  else:
                       return self.builder.icmp_unsigned(op, llvm_left, llvm_right, name="ucmp")
             else:
                  # Se os tipos originais não forem ambos ponteiros ou ambos inteiros, a comparação é inválida
                  self.add_error(f"Comparação '{op}' entre tipos incompatíveis: {self.type_to_string(left_concrete_orig)} e {self.type_to_string(right_concrete_orig)}", node)
                  return None
        elif op in ('&', '|', '^', '<<', '>>'):
             # ... (lógica bitwise/shift, usa llvm_left, llvm_right ajustados) ...
             if isinstance(final_op_type, ir.IntType) and isinstance(llvm_right.type, ir.IntType):
                if op == '&': return self.builder.and_(llvm_left, llvm_right)
                if op == '|': return self.builder.or_(llvm_left, llvm_right)
                if op == '^': return self.builder.xor(llvm_left, llvm_right)
                if op == '<<': return self.builder.shl(llvm_left, llvm_right)
                else: # >>
                    is_signed = self.is_signed_type_heuristic(getattr(node.left, 'atom_type', None), final_op_type)
                    return self.builder.ashr(llvm_left, llvm_right) if is_signed else self.builder.lshr(llvm_left, llvm_right)
             else: self.add_error(...); return None
        else: self.add_error(...); return None

    def _generate_logical_binary_op(self, node: ast.BinaryOp) -> Optional[ir.Value]:
        # ... (código como antes) ...
        op = node.op
        if not self.builder or (self.builder.block and self.builder.block.is_terminated): self.add_error(...); return None
        bool_type = self.llvm_types.get('bool')
        if not bool_type or not isinstance(bool_type, ir.IntType) or bool_type.width != 1: self.add_error(...); return None
        current_function = self.builder.function
        eval_b_block = current_function.append_basic_block(name=f"op.{op}.eval_b")
        merge_block = current_function.append_basic_block(name=f"op.{op}.merge")
        llvm_left = self.visit(node.left, expected_llvm_type=bool_type)
        if llvm_left is None: return None
        if llvm_left.type != bool_type:
            if isinstance(llvm_left.type, ir.IntType): llvm_left = self.builder.icmp_unsigned('!=', llvm_left, ir.Constant(llvm_left.type, 0))
            else: self.add_error(...); return None
        after_a_block = self.builder.block
        if op == '||': self.builder.cbranch(llvm_left, merge_block, eval_b_block)
        else: self.builder.cbranch(llvm_left, eval_b_block, merge_block)
        self.builder.position_at_end(eval_b_block)
        llvm_right = self.visit(node.right, expected_llvm_type=bool_type)
        if llvm_right is None: return None
        if llvm_right.type != bool_type:
            if isinstance(llvm_right.type, ir.IntType): llvm_right = self.builder.icmp_unsigned('!=', llvm_right, ir.Constant(llvm_right.type, 0))
            else: self.add_error(...); return None
        after_b_block = self.builder.block
        if not self.builder.block.is_terminated: self.builder.branch(merge_block)
        self.builder.position_at_end(merge_block)
        phi_node = self.builder.phi(bool_type, name=f"op.{op}.result")
        if op == '||': phi_node.add_incoming(ir.Constant(bool_type, 1), after_a_block)
        else: phi_node.add_incoming(ir.Constant(bool_type, 0), after_a_block)
        if llvm_right: phi_node.add_incoming(llvm_right, after_b_block)
        return phi_node


    def visit_FieldAccess(self, node: ast.FieldAccess, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
        # ... (código como antes, chama visit_lvalue_pointer e depois load) ...
        field_name = node.field.name
        if not self.builder or (self.builder.block and self.builder.block.is_terminated): self.add_error(...); return None
        llvm_field_ptr = self.visit_lvalue_pointer(node) # visit_lvalue_pointer faz o bounds check implícito se necessário
        if llvm_field_ptr is None: self.add_error(f"Falha ponteiro campo '{field_name}'.", node); return None
        if not isinstance(llvm_field_ptr.type, ir.PointerType): self.add_error(...); return None
        # Para .len de slice, o ponteiro já é do tipo correto (usize*), apenas carrega
        # Para campos de struct, carrega o valor do tipo do campo
        return self.builder.load(llvm_field_ptr, name=field_name + ".load")

    def visit_IndexAccess(self, node: ast.IndexAccess, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
        # ... (código como antes, chama visit_lvalue_pointer e depois load) ...
        if not self.builder or (self.builder.block and self.builder.block.is_terminated): self.add_error(...); return None
        llvm_element_ptr = self.visit_lvalue_pointer(node) # visit_lvalue_pointer faz o bounds check
        if llvm_element_ptr is None: self.add_error(f"Falha ponteiro elemento IndexAccess.", node); return None
        if not isinstance(llvm_element_ptr.type, ir.PointerType): self.add_error(...); return None
        return self.builder.load(llvm_element_ptr, name="idx.load")

    def visit_CastExpr(self, node: ast.CastExpr, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
        # ... (código como antes) ...
        if not self.builder or (self.builder.block and self.builder.block.is_terminated): self.add_error(...); return None
        llvm_target_type = self.get_llvm_type(node.target_type)
        if llvm_target_type is None: self.add_error(...); return None
        llvm_source_value = self.visit(node.expr) # Não passa target type aqui, cast é explícito
        if llvm_source_value is None: self.add_error(...); return None
        llvm_source_type = llvm_source_value.type
        if llvm_source_type == llvm_target_type: return llvm_source_value
        if isinstance(llvm_source_type, ir.IntType) and isinstance(llvm_target_type, ir.IntType):
            source_bits = llvm_source_type.width; target_bits = llvm_target_type.width
            if target_bits < source_bits: return self.builder.trunc(llvm_source_value, llvm_target_type)
            elif target_bits > source_bits:
                is_signed = self.is_signed_type_heuristic(getattr(node.expr, 'atom_type', None), llvm_source_type)
                return self.builder.sext(llvm_source_value, llvm_target_type) if is_signed else self.builder.zext(llvm_source_value, llvm_target_type)
            else: return self.builder.bitcast(llvm_source_value, llvm_target_type)
        elif isinstance(llvm_source_type, ir.PointerType) and isinstance(llvm_target_type, ir.PointerType):
             return self.builder.bitcast(llvm_source_value, llvm_target_type)
        elif isinstance(llvm_source_type, ir.IntType) and isinstance(llvm_target_type, ir.PointerType):
             return self.builder.inttoptr(llvm_source_value, llvm_target_type)
        elif isinstance(llvm_source_type, ir.PointerType) and isinstance(llvm_target_type, ir.IntType):
             return self.builder.ptrtoint(llvm_source_value, llvm_target_type)
        # REMOVIDO: Float casts
        else: self.add_error(f"Cast não suportado.", node); return None


    def visit_FunctionCall(self, node: ast.FunctionCall, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
        if not self.builder or not self.builder.block or self.builder.block.is_terminated:
            self.add_error("Builder inativo/terminado para FunctionCall.", node); return None

        llvm_callee_val = self.visit(node.callee) # Visita a expressão callee
        if llvm_callee_val is None: self.add_error("Falha ao gerar callee.", node.callee); return None

        the_callable_llvm_val: ir.Value
        actual_func_type_llvm: Optional[ir.FunctionType] = None

        if isinstance(llvm_callee_val, ir.Function): # Caso 1: Chamando função global/externa diretamente
             the_callable_llvm_val = llvm_callee_val
             actual_func_type_llvm = llvm_callee_val.function_type
        elif isinstance(llvm_callee_val.type, ir.PointerType) and isinstance(llvm_callee_val.type.pointee, ir.FunctionType): # Caso 2: Chamando ponteiro para função
             the_callable_llvm_val = llvm_callee_val # Usa o valor do ponteiro diretamente
             actual_func_type_llvm = llvm_callee_val.type.pointee
        else: # Erro: Não é chamável
             self.add_error(f"Expressão não é chamável (tipo LLVM: {llvm_callee_val.type}).", node.callee)
             return None

        # ... (Processamento de argumentos e casts como antes) ...
        llvm_args = []
        num_expected_named_params = len(actual_func_type_llvm.args)
        is_vararg_func = actual_func_type_llvm.var_arg
        for i, arg_node_ast in enumerate(node.args):
             expected_arg_llvm_type: Optional[ir.Type] = actual_func_type_llvm.args[i] if i < num_expected_named_params else None
             llvm_arg_val = self.visit(arg_node_ast, expected_llvm_type=expected_arg_llvm_type)
             if llvm_arg_val is None: self.add_error(f"Falha arg {i}", arg_node_ast); return None
             # ... (lógica de cast de argumento) ...
             if expected_arg_llvm_type and llvm_arg_val.type != expected_arg_llvm_type:
                 casted_arg_val = None # ... (lógica de cast) ...
                 if isinstance(llvm_arg_val.type, ir.IntType) and isinstance(expected_arg_llvm_type, ir.IntType):
                    is_signed = self.is_signed_type_heuristic(getattr(arg_node_ast,'atom_type',None), llvm_arg_val.type)
                    if expected_arg_llvm_type.width > llvm_arg_val.type.width: casted_arg_val = self.builder.sext(llvm_arg_val, expected_arg_llvm_type) if is_signed else self.builder.zext(llvm_arg_val, expected_arg_llvm_type)
                    elif expected_arg_llvm_type.width < llvm_arg_val.type.width: casted_arg_val = self.builder.trunc(llvm_arg_val, expected_arg_llvm_type)
                    else: casted_arg_val = self.builder.bitcast(llvm_arg_val, expected_arg_llvm_type)
                 elif isinstance(llvm_arg_val.type, ir.PointerType) and isinstance(expected_arg_llvm_type, ir.PointerType):
                    casted_arg_val = self.builder.bitcast(llvm_arg_val, expected_arg_llvm_type)
                 elif isinstance(llvm_arg_val.type, ir.ArrayType) and isinstance(expected_arg_llvm_type, ir.PointerType): # Array decay
                    temp_alloca = self.builder.alloca(llvm_arg_val.type); self.builder.store(llvm_arg_val, temp_alloca)
                    zero_idx = ir.Constant(ir.IntType(32),0)
                    decayed_ptr = self.builder.gep(temp_alloca, [zero_idx, zero_idx])
                    if decayed_ptr.type != expected_arg_llvm_type: casted_arg_val = self.builder.bitcast(decayed_ptr, expected_arg_llvm_type)
                    else: casted_arg_val = decayed_ptr
                 elif isinstance(llvm_arg_val.type, (ir.LiteralStructType, ir.IdentifiedStructType)) and \
                      hasattr(llvm_arg_val.type, 'elements') and len(llvm_arg_val.type.elements) == 2 and \
                      isinstance(expected_arg_llvm_type, ir.PointerType): # Slice -> Ptr
                      if isinstance(llvm_arg_val.type.elements[0], ir.PointerType):
                          ptr_field = self.builder.extract_value(llvm_arg_val, 0)
                          if ptr_field.type != expected_arg_llvm_type: casted_arg_val = self.builder.bitcast(ptr_field, expected_arg_llvm_type)
                          else: casted_arg_val = ptr_field
                 if casted_arg_val: llvm_arg_val = casted_arg_val
                 else: self.add_error(f"Cast arg {i} inválido", arg_node_ast); return None

             llvm_args.append(llvm_arg_val)

        # ... (verificação do número de argumentos) ...
        if not is_vararg_func and len(llvm_args) != num_expected_named_params: self.add_error(...); return None
        if is_vararg_func and len(llvm_args) < num_expected_named_params: self.add_error(...); return None

        call_name = "calltmp" if not isinstance(actual_func_type_llvm.return_type, ir.VoidType) else ""
        try:
            # Chama usando a referência direta (the_callable_llvm_val)
            call_result = self.builder.call(the_callable_llvm_val, llvm_args, name=call_name)
            return None if isinstance(actual_func_type_llvm.return_type, ir.VoidType) else call_result
        except Exception as e:
             self.add_error(f"Falha ao gerar CALL: {e}", node); traceback.print_exc(); return None


    def visit_ByteStringLiteral(self, node: ast.ByteStringLiteral, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
        # ... (código como antes) ...
        if not self.builder: self.add_error(...); return None
        actual_bytes = node.value; # ... (check bytes type) ...
        global_byte_array_var = create_global_byte_array_constant(self.module, actual_bytes)
        zero_i32 = ir.Constant(ir.IntType(32), 0)
        ptr_to_first_byte_const = global_byte_array_var.gep([zero_i32, zero_i32])
        usize_type = self.llvm_types.get('usize'); # ... (check usize_type) ...
        len_value_const = ir.Constant(usize_type, len(actual_bytes))
        u8_ptr_type = ir.PointerType(ir.IntType(8))
        default_slice_llvm_type = ir.LiteralStructType([u8_ptr_type, usize_type])
        final_slice_llvm_type = default_slice_llvm_type
        if isinstance(expected_llvm_type, (ir.LiteralStructType, ir.IdentifiedStructType)) and \
           hasattr(expected_llvm_type, 'elements') and len(expected_llvm_type.elements) == 2 and \
           expected_llvm_type.elements[0] == u8_ptr_type and \
           expected_llvm_type.elements[1] == usize_type: final_slice_llvm_type = expected_llvm_type
        elif expected_llvm_type is not None: self.add_error(...) # Pode precisar de cast
        undef_slice_val = ir.Constant(final_slice_llvm_type, None)
        agg_with_ptr = self.builder.insert_value(undef_slice_val, ptr_to_first_byte_const, 0)
        final_slice_value = self.builder.insert_value(agg_with_ptr, len_value_const, 1)
        return final_slice_value


    def visit_ArrayLiteral(self, node: ast.ArrayLiteral, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
        # ... (código como antes) ...
        if not self.builder: self.add_error(...); return None
        llvm_elements = []
        element_llvm_type_final: Optional[ir.Type] = None
        expected_element_type_from_context: Optional[ir.Type] = None
        if isinstance(expected_llvm_type, ir.ArrayType):
            expected_element_type_from_context = expected_llvm_type.element
            if len(node.elements) != expected_llvm_type.count: self.add_error(...); return None
        if not node.elements:
            if isinstance(expected_llvm_type, ir.ArrayType): return ir.Constant(expected_llvm_type, None)
            else: self.add_error(...); return None
        for i, el_node_ast in enumerate(node.elements):
            current_expected_elem_type_for_visit = expected_element_type_from_context if expected_element_type_from_context else element_llvm_type_final
            llvm_el_val = self.visit(el_node_ast, expected_llvm_type=current_expected_elem_type_for_visit)
            if llvm_el_val is None: self.add_error(...); return None
            if i == 0: # Primeiro elemento
                element_llvm_type_final = llvm_el_val.type
                if expected_element_type_from_context and element_llvm_type_final != expected_element_type_from_context:
                    casted_el = None # ... (lógica de cast) ...
                    if isinstance(llvm_el_val.type, ir.IntType) and isinstance(expected_element_type_from_context, ir.IntType):
                        is_signed = self.is_signed_type_heuristic(getattr(el_node_ast,'atom_type',None), llvm_el_val.type)
                        if expected_element_type_from_context.width > llvm_el_val.type.width: casted_el = self.builder.sext(llvm_el_val, expected_element_type_from_context) if is_signed else self.builder.zext(llvm_el_val, expected_element_type_from_context)
                        elif expected_element_type_from_context.width < llvm_el_val.type.width: casted_el = self.builder.trunc(llvm_el_val, expected_element_type_from_context)
                        else: casted_el = self.builder.bitcast(llvm_el_val, expected_element_type_from_context)
                    if casted_el: llvm_el_val = casted_el; element_llvm_type_final = casted_el.type
                    else: self.add_error(...); return None
            elif element_llvm_type_final and llvm_el_val.type != element_llvm_type_final: # Elementos subsequentes
                casted_el = None # ... (lógica de cast) ...
                if isinstance(llvm_el_val.type, ir.IntType) and isinstance(element_llvm_type_final, ir.IntType):
                    is_signed = self.is_signed_type_heuristic(getattr(el_node_ast,'atom_type',None), llvm_el_val.type)
                    if element_llvm_type_final.width > llvm_el_val.type.width: casted_el = self.builder.sext(llvm_el_val, element_llvm_type_final) if is_signed else self.builder.zext(llvm_el_val, element_llvm_type_final)
                    elif element_llvm_type_final.width < llvm_el_val.type.width: casted_el = self.builder.trunc(llvm_el_val, element_llvm_type_final)
                    else: casted_el = self.builder.bitcast(llvm_el_val, element_llvm_type_final)
                if casted_el: llvm_el_val = casted_el
                else: self.add_error(...); return None
            llvm_elements.append(llvm_el_val)
        if element_llvm_type_final is None: self.add_error(...); return None
        final_array_llvm_type = ir.ArrayType(element_llvm_type_final, len(llvm_elements))
        if expected_llvm_type and final_array_llvm_type != expected_llvm_type: self.add_error(...); return None
        undef_array_val = ir.Constant(final_array_llvm_type, None)
        current_agg_val = undef_array_val
        for i, llvm_elem_to_insert in enumerate(llvm_elements):
            current_agg_val = self.builder.insert_value(current_agg_val, llvm_elem_to_insert, i, name=f"arr.elem{i}")
        return current_agg_val


    def visit_ArrayRepeatExpr(self, node: ast.ArrayRepeatExpr, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
         # ... (código como antes) ...
         if not self.builder: self.add_error(...); return None
         const_size_val = self.evaluate_constant_expression(node.size, self.llvm_types.get('usize'))
         if not (isinstance(const_size_val, ir.Constant) and isinstance(const_size_val.type, ir.IntType)): self.add_error(...); return None
         array_size = const_size_val.constant
         expected_element_type_from_context: Optional[ir.Type] = None
         if isinstance(expected_llvm_type, ir.ArrayType):
             expected_element_type_from_context = expected_llvm_type.element
             if expected_llvm_type.count != array_size: self.add_error(...); return None
         llvm_val_to_repeat = self.visit(node.value, expected_llvm_type=expected_element_type_from_context)
         if llvm_val_to_repeat is None: self.add_error(...); return None
         element_llvm_type_final = llvm_val_to_repeat.type
         if expected_element_type_from_context and element_llvm_type_final != expected_element_type_from_context:
             casted_val = None # ... (lógica de cast) ...
             if isinstance(element_llvm_type_final, ir.IntType) and isinstance(expected_element_type_from_context, ir.IntType):
                is_signed = self.is_signed_type_heuristic(getattr(node.value,'atom_type',None), element_llvm_type_final)
                if expected_element_type_from_context.width > element_llvm_type_final.width: casted_val = self.builder.sext(llvm_val_to_repeat, expected_element_type_from_context) if is_signed else self.builder.zext(llvm_val_to_repeat, expected_element_type_from_context)
                elif expected_element_type_from_context.width < element_llvm_type_final.width: casted_val = self.builder.trunc(llvm_val_to_repeat, expected_element_type_from_context)
                else: casted_val = self.builder.bitcast(llvm_val_to_repeat, expected_element_type_from_context)
             if casted_val: llvm_val_to_repeat = casted_val; element_llvm_type_final = casted_val.type
             else: self.add_error(...); return None
         final_array_llvm_type = ir.ArrayType(element_llvm_type_final, array_size)
         if expected_llvm_type and final_array_llvm_type != expected_llvm_type : self.add_error(...); return None
         undef_array_val = ir.Constant(final_array_llvm_type, None)
         current_agg_val = undef_array_val
         for i in range(array_size):
             current_agg_val = self.builder.insert_value(current_agg_val, llvm_val_to_repeat, i, name=f"repeat.elem{i}")
         return current_agg_val


    def visit_StructLiteral(self, node: ast.StructLiteral, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
        # ... (código como antes) ...
        struct_type_name = node.type_name.name
        if not self.builder: self.add_error(...); return None
        llvm_struct_type: Optional[Union[ir.IdentifiedStructType, ir.LiteralStructType]] = None
        if isinstance(expected_llvm_type, ir.IdentifiedStructType) and hasattr(expected_llvm_type, 'name') and expected_llvm_type.name == struct_type_name: llvm_struct_type = expected_llvm_type
        elif struct_type_name in self.llvm_defined_structs: llvm_struct_type = self.llvm_defined_structs[struct_type_name]
        else:
            temp_custom_type_ast = ast.CustomType(name=node.type_name); llvm_struct_type = self.get_llvm_type(temp_custom_type_ast)
            if not llvm_struct_type or not isinstance(llvm_struct_type, ir.IdentifiedStructType): self.add_error(...); return None
        if not hasattr(llvm_struct_type, 'elements') or llvm_struct_type.is_opaque: self.add_error(...); return None
        struct_def_node_ast = self.atom_struct_defs.get(struct_type_name)
        if not struct_def_node_ast or len(node.fields) != len(struct_def_node_ast.fields): self.add_error(...); return None
        undef_struct_val = ir.Constant(llvm_struct_type, None)
        literal_fields_map_ast = {f.name.name: f.value for f in node.fields}
        current_agg_val = undef_struct_val
        for i, field_def_ast in enumerate(struct_def_node_ast.fields):
            field_name = field_def_ast.name.name
            field_llvm_type_expected = llvm_struct_type.elements[i]
            if field_name not in literal_fields_map_ast: self.add_error(...); return None
            field_value_node_ast = literal_fields_map_ast[field_name]
            llvm_field_val = self.visit(field_value_node_ast, expected_llvm_type=field_llvm_type_expected)
            if llvm_field_val is None: self.add_error(...); return None
            if llvm_field_val.type != field_llvm_type_expected: # Cast check
                casted_field_val = None # ... (lógica de cast, incluindo slice->slice) ...
                if isinstance(llvm_field_val.type, ir.IntType) and isinstance(field_llvm_type_expected, ir.IntType):
                    is_signed = self.is_signed_type_heuristic(getattr(field_value_node_ast,'atom_type',None), llvm_field_val.type)
                    if field_llvm_type_expected.width > llvm_field_val.type.width: casted_field_val = self.builder.sext(llvm_field_val, field_llvm_type_expected) if is_signed else self.builder.zext(llvm_field_val, field_llvm_type_expected)
                    elif field_llvm_type_expected.width < llvm_field_val.type.width: casted_field_val = self.builder.trunc(llvm_field_val, field_llvm_type_expected)
                    else: casted_field_val = self.builder.bitcast(llvm_field_val, field_llvm_type_expected)
                elif isinstance(llvm_field_val.type, ir.PointerType) and isinstance(field_llvm_type_expected, ir.PointerType):
                     casted_field_val = self.builder.bitcast(llvm_field_val, field_llvm_type_expected)
                elif isinstance(llvm_field_val.type, (ir.LiteralStructType, ir.IdentifiedStructType)) and \
                     isinstance(field_llvm_type_expected, (ir.LiteralStructType, ir.IdentifiedStructType)) and \
                     hasattr(field_llvm_type_expected, 'elements') and hasattr(llvm_field_val.type, 'elements') and \
                     len(llvm_field_val.type.elements) == 2 and len(field_llvm_type_expected.elements) == 2 and \
                     isinstance(llvm_field_val.type.elements[0], ir.PointerType) and isinstance(field_llvm_type_expected.elements[0], ir.PointerType) and \
                     llvm_field_val.type.elements[1] == self.llvm_types['usize'] and field_llvm_type_expected.elements[1] == self.llvm_types['usize']:
                    ptr_field_rhs = self.builder.extract_value(llvm_field_val, 0)
                    len_field_rhs = self.builder.extract_value(llvm_field_val, 1)
                    casted_ptr_field = ptr_field_rhs
                    if ptr_field_rhs.type != field_llvm_type_expected.elements[0]:
                        casted_ptr_field = self.builder.bitcast(ptr_field_rhs, field_llvm_type_expected.elements[0])
                    temp_agg = ir.Constant(field_llvm_type_expected, None)
                    temp_agg = self.builder.insert_value(temp_agg, casted_ptr_field, 0)
                    casted_field_val = self.builder.insert_value(temp_agg, len_field_rhs, 1)
                if casted_field_val: llvm_field_val = casted_field_val
                else: self.add_error(...); return None
            current_agg_val = self.builder.insert_value(current_agg_val, llvm_field_val, i, name=f"{struct_type_name}.{field_name}")
        return current_agg_val


    def visit_NamespaceAccess(self, node: ast.NamespaceAccess, expected_llvm_type: Optional[ir.Type] = None) -> Optional[ir.Value]:
        # ... (código como antes) ...
        variant_value = getattr(node, 'resolved_variant_value', None)
        enum_def_node = getattr(node, 'resolved_enum_def_node', None)
        if variant_value is None or not isinstance(enum_def_node, ast.EnumDef): self.add_error(...); return None
        i32_type = self.llvm_types.get('i32'); # ... (check i32_type) ...
        const_val = ir.Constant(i32_type, variant_value)
        if expected_llvm_type and const_val.type != expected_llvm_type and self.builder: # Cast check
            if isinstance(expected_llvm_type, ir.IntType) and isinstance(const_val.type, ir.IntType):
                if expected_llvm_type.width < const_val.type.width: return self.builder.trunc(const_val, expected_llvm_type)
                elif expected_llvm_type.width > const_val.type.width: return self.builder.zext(const_val, expected_llvm_type)
                elif const_val.type != expected_llvm_type: return self.builder.bitcast(const_val, expected_llvm_type)
        return const_val

# --- Função Principal para Geração ---
def generate_llvm_ir(program_node: ast.Program) -> str:
    generator = CodeGenVisitor()
    llvm_ir_string = generator.generate_code(program_node)
    return llvm_ir_string
