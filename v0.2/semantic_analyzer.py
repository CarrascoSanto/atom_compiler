# semantic_analyzer.py (CORRIGIDO - Parâmetro visit_lvalue)

import ast_nodes as ast
from ast_nodes import ( # Importações explícitas
    Node, Expression, Statement, Type, Program, FunctionDef, FunctionDecl,
    StructDef, EnumDef, ConstDef, ExternBlock, ImportDecl, LetBinding, MutBinding,
    Assignment, Parameter, CustomType, PointerType, ReferenceType, ArrayType,
    SliceType, PrimitiveType, UnitType, LiteralIntegerType, Identifier,
    IntegerLiteral, FunctionType, BooleanLiteral, CharLiteral, StringLiteral,
    ByteStringLiteral, ArrayLiteral, StructLiteral, UnaryOp, BinaryOp,
    FieldAccess, IndexAccess, CastExpr, FunctionCall,
    Underscore, ExpressionStatement, ReturnStmt, IfStmt, WhileStmt, LoopStmt, BreakStmt, ContinueStmt, MemBlock, EMemBlock
)
from typing import Dict, List, Optional, Union, Tuple, Set
import traceback

class SemanticAnalyzer:
    def __init__(self):
        self.errors: List[str] = []
        self.global_scope: Dict[str, ast.Node] = {}
        self.struct_defs: Dict[str, ast.StructDef] = {}
        self.enum_defs: Dict[str, ast.EnumDef] = {}
        self.enum_variant_values: Dict[str, Dict[str, int]] = {}
        self.local_scopes: List[Dict[str, ast.Node]] = []
        self.current_function_return_type: Optional[ast.Type] = None
        self.current_function_name: Optional[str] = None
        self.is_in_mem_block: bool = False
        self.llvm_types = {"int", "uint", "bool", "char", "i8", "u8", "i16", "u16", "i32", "u32", "i64", "u64", "usize", "isize", "f32", "f64"}
        self.integer_types = {"int", "uint", "i8", "u8", "i16", "u16", "i32", "u32", "i64", "u64", "usize", "isize"}
        self.numeric_types = self.integer_types | {"f32", "f64"}
        self.current_loop_level: int = 0


    def type_to_string(self, type_node: Optional[ast.Type]) -> str:
        if type_node is None: return "<erro_interno_tipo_None>"
        try:
            resolved = self._resolve_type(type_node)
            return repr(resolved if resolved else type_node)
        except Exception as e:
            return f"<repr_falhou:{type(type_node).__name__}:{e}>"

    def add_error(self, message: str, node: Optional[ast.Node] = None):
        pos_info = ""
        if node and hasattr(node, 'meta') and hasattr(node.meta, 'line'):
            pos_info = f" (linha {node.meta.line}, col {getattr(node.meta, 'column', '?')})"
        full_message = f"Erro Semântico{pos_info}: {message}"
        if full_message not in self.errors:
            self.errors.append(full_message)
            print(f"SEMANTIC ERROR:{pos_info} {message}")

    def check_unsafe_context(self, operation_desc: str, node: ast.Node):
        if not self.is_in_mem_block:
            self.add_error(f"Operação insegura '{operation_desc}' requer um bloco 'mem'", node)
            return False
        return True

    def enter_scope(self):
         self.local_scopes.append({})
    def exit_scope(self):
         if self.local_scopes: self.local_scopes.pop()

    def declare_local(self, name: str, node: Union[ast.LetBinding, ast.MutBinding, ast.Parameter]) -> bool:
         if not self.local_scopes: self.add_error(f"Erro Interno: Declarar local '{name}' fora de escopo.", node); return False
         current_local_scope = self.local_scopes[-1]
         if name in current_local_scope: return False
         current_local_scope[name] = node
         return True

    def lookup_local(self, name: str) -> Optional[Union[ast.LetBinding, ast.MutBinding, ast.Parameter]]:
         for scope in reversed(self.local_scopes):
              if name in scope:
                   found_node = scope[name]
                   if isinstance(found_node, (ast.LetBinding, ast.MutBinding, ast.Parameter)): return found_node
                   else: self.add_error(f"Erro Interno: Nó local inesperado '{type(found_node).__name__}' para '{name}'."); return None
         return None

    def lookup_symbol_node(self, name: str) -> Optional[ast.Node]:
         local_found_node = self.lookup_local(name)
         if local_found_node: return local_found_node
         global_found_node = self.global_scope.get(name)
         if global_found_node: return global_found_node
         return None

    def analyze(self, program_node: ast.Program) -> List[str]:
        self.errors = []
        self.global_scope = {}
        self.struct_defs = {}
        self.enum_defs = {}
        self.local_scopes = []
        self.current_function_return_type = None
        self.current_function_name = None
        self.is_in_mem_block = False
        self.current_loop_level = 0

        for item in program_node.body:
            if isinstance(item, ast.StructDef):
                type_name = item.name.name
                if type_name in self.global_scope: self.add_error(f"Tipo '{type_name}' já definido", item.name); continue
                self.global_scope[type_name] = item
                self.struct_defs[type_name] = item
            elif isinstance(item, ast.EnumDef):
                type_name = item.name.name
                if type_name in self.global_scope: self.add_error(f"Tipo '{type_name}' já definido", item.name); continue
                self.global_scope[type_name] = item
                self.enum_defs[type_name] = item
                self.enum_variant_values[type_name] = {}
                next_value = 0; variant_names_seen = set()
                for variant_node in item.variants:
                    variant_name = variant_node.name.name
                    if variant_name in variant_names_seen: self.add_error(f"Variante '{variant_name}' duplicada em '{type_name}'", variant_node.name); continue
                    variant_names_seen.add(variant_name)
                    setattr(variant_node, 'value', next_value)
                    self.enum_variant_values[type_name][variant_name] = next_value
                    next_value += 1

        for item in program_node.body:
            name_to_declare: Optional[str] = None; node_for_scope: Optional[ast.Node] = None; is_function_like = False
            if isinstance(item, ast.FunctionDef):
                name_to_declare = item.name.name; node_for_scope = item; is_function_like = True
                if not self._validate_signature_types(item): continue
            elif isinstance(item, ast.ConstDef):
                name_to_declare = item.name.name; node_for_scope = item
                resolved_type = self._resolve_type(item.type_annot)
                if not resolved_type: self.add_error(f"Tipo inválido para constante '{name_to_declare}'", item.type_annot)
                else: setattr(item, 'resolved_type', resolved_type)
            elif isinstance(item, ast.ExternBlock):
                for decl in item.declarations:
                    func_name = decl.name.name
                    if func_name in self.global_scope and not isinstance(self.global_scope[func_name], (ast.StructDef, ast.EnumDef)):
                        self.add_error(f"Nome global '{func_name}' (extern) já definido", decl.name); continue
                    if self._validate_signature_types(decl):
                        self.global_scope[func_name] = decl
                        setattr(decl, 'is_extern', True); setattr(decl, 'is_var_arg_resolved', getattr(decl, 'is_var_arg', False))
                continue
            if name_to_declare and node_for_scope:
                if name_to_declare in self.global_scope:
                    existing_node = self.global_scope[name_to_declare]
                    if is_function_like and isinstance(existing_node, (ast.StructDef, ast.EnumDef)):
                         self.global_scope[name_to_declare] = node_for_scope
                    else: self.add_error(f"Nome global '{name_to_declare}' já definido", getattr(node_for_scope, 'name', node_for_scope))
                else: self.global_scope[name_to_declare] = node_for_scope

        for item in program_node.body:
            if isinstance(item, (ast.FunctionDef, ast.ConstDef, ast.StructDef, ast.EnumDef)):
                 self.visit(item)
            elif isinstance(item, (ast.ExternBlock, ast.ImportDecl)): pass
            else: self.add_error(f"Item top-level inesperado: {type(item).__name__}", item)
        return self.errors

    def _validate_signature_types(self, node: Union[ast.FunctionDef, ast.FunctionDecl]) -> bool:
        valid = True
        for i, param in enumerate(node.params):
            param_type_node = param.type
            resolved_param_type = self._resolve_type(param_type_node)
            if not resolved_param_type:
                self.add_error(f"Tipo do parâmetro {i+1} ('{self.type_to_string(param_type_node)}') inválido na assinatura de '{node.name.name}'", param_type_node)
                valid = False
            else: setattr(param, 'resolved_type', resolved_param_type)
        return_type_node = node.return_type
        resolved_return_type = self._resolve_type(return_type_node)
        if not resolved_return_type:
            self.add_error(f"Tipo de retorno ('{self.type_to_string(return_type_node)}') inválido na assinatura de '{node.name.name}'", return_type_node)
            valid = False
        else: setattr(node, 'resolved_return_type', resolved_return_type)
        return valid

    def visit(self, node: Optional[ast.Node]) -> Optional[ast.Type]:
        if node is None: return None
        method_name = f'visit_{node.__class__.__name__}'
        visitor_method = getattr(self, method_name, self.generic_visit)
        try:
            result = visitor_method(node)
            if isinstance(node, ast.Expression) and isinstance(result, ast.Type):
                 setattr(node, 'atom_type', result)
            return result
        except Exception as e:
             self.add_error(f"Erro interno no visitor '{method_name}' para {type(node).__name__}: {e}", node)
             traceback.print_exc()
             if isinstance(node, ast.Expression): setattr(node, 'atom_type', ast.PrimitiveType("_error_"))
             return None

    def generic_visit(self, node: ast.Node):
        if hasattr(node, '__dataclass_fields__'):
            for field_name in node.__dataclass_fields__:
                field_value = getattr(node, field_name)
                if isinstance(field_value, list):
                    for item_in_list in field_value: # Renomeado para evitar conflito
                        if isinstance(item_in_list, ast.Node): self.visit(item_in_list)
                elif isinstance(field_value, ast.Node):
                    self.visit(field_value)
        return None

    def visit_Program(self, node: ast.Program): pass
    def visit_StructDef(self, node: ast.StructDef):
        for field in node.fields:
            resolved_field_type = self._resolve_type(field.type)
            if not resolved_field_type: self.add_error(f"Tipo '{self.type_to_string(field.type)}' do campo '{field.name.name}' em struct '{node.name.name}' inválido.", field.type)
            else: setattr(field, 'resolved_type', resolved_field_type)
        return None
    def visit_EnumDef(self, node: ast.EnumDef): return None

    def visit_ConstDef(self, node: ast.ConstDef):
        expected_type = getattr(node, 'resolved_type', self._resolve_type(node.type_annot))
        if not expected_type or (isinstance(expected_type, PrimitiveType) and expected_type.name == "_error_"): return None
        value_type_maybe_literal = self.visit(node.value)
        if value_type_maybe_literal is None: return None
        if not self.is_constant_expression(node.value): self.add_error(f"Inicializador da constante '{node.name.name}' não é uma expressão constante.", node.value)
        if not self.check_type_compatibility(expected_type, value_type_maybe_literal, node.value):
            self.add_error(f"Tipo do valor ({self.type_to_string(value_type_maybe_literal)}) incompatível com anotação ({self.type_to_string(expected_type)}) da constante '{node.name.name}'", node.value)
        return None

    def visit_FunctionDef(self, node: ast.FunctionDef):
        resolved_return_type = getattr(node, 'resolved_return_type', None)
        if not resolved_return_type: return None
        outer_func_ret_type = self.current_function_return_type; outer_func_name = self.current_function_name
        self.current_function_return_type = resolved_return_type; self.current_function_name = node.name.name
        self.enter_scope()
        valid_params = True
        for param in node.params:
            param_name = param.name.name
            resolved_type = getattr(param, 'resolved_type', None)
            if not resolved_type: self.add_error(f"Erro interno: tipo do parâmetro '{param_name}' não resolvido.", param); valid_params = False; continue
            if not self.declare_local(param_name, param): self.add_error(f"Parâmetro '{param_name}' redeclarado.", param.name); valid_params = False
        if not valid_params: self.exit_scope(); self.current_function_return_type = outer_func_ret_type; self.current_function_name = outer_func_name; return None
        for stmt in node.body: self.visit(stmt)
        self.exit_scope()
        self.current_function_return_type = outer_func_ret_type; self.current_function_name = outer_func_name
        return None

    def visit_LetBinding(self, node: ast.LetBinding):
        var_name = node.name.name
        rhs_type_maybe_literal = self.visit(node.value)
        if rhs_type_maybe_literal is None:
            setattr(node, 'declared_type', ast.PrimitiveType("_error_"))
            self.declare_local(var_name, node); return None
        annot_type: Optional[ast.Type] = None
        if node.type_annot:
            annot_type = self._resolve_type(node.type_annot)
            if not annot_type: annot_type = ast.PrimitiveType("_error_")
        final_type: Optional[ast.Type] = None
        if annot_type:
            if not self.check_type_compatibility(annot_type, rhs_type_maybe_literal, node.value):
                self.add_error(f"Tipo valor ({self.type_to_string(rhs_type_maybe_literal)}) incompatível com anotação ({self.type_to_string(annot_type)}) para 'let {var_name}'", node.value) # Erro no valor
            final_type = annot_type
        else:
            resolved_rhs_type = self.get_concrete_type(rhs_type_maybe_literal)
            if resolved_rhs_type is None or isinstance(resolved_rhs_type, UnitType):
                 self.add_error(f"Não é possível inferir tipo ou usar '()' para 'let {var_name}'. Use uma anotação de tipo.", node.value); final_type = ast.PrimitiveType("_error_")
            elif isinstance(resolved_rhs_type, ast.ArrayType) and isinstance(resolved_rhs_type.element_type, ast.PrimitiveType) and resolved_rhs_type.element_type.name == "_empty_array_":
                 self.add_error(f"Não é possível inferir o tipo de `[]` para 'let {var_name}'. Use uma anotação de tipo (ex: `let arr: [i32; 0] = [];`).", node.value); final_type = ast.PrimitiveType("_error_")
            else: final_type = resolved_rhs_type
        setattr(node, 'declared_type', final_type)
        if not self.declare_local(var_name, node): self.add_error(f"Variável 'let {var_name}' já declarada neste escopo.", node.name)
        return None

    def visit_MutBinding(self, node: ast.MutBinding):
        var_name = node.name.name
        rhs_type_maybe_literal = self.visit(node.value)
        if rhs_type_maybe_literal is None:
            setattr(node, 'declared_type', ast.PrimitiveType("_error_"))
            self.declare_local(var_name, node); return None
        annot_type: Optional[ast.Type] = None
        if node.type_annot:
            annot_type = self._resolve_type(node.type_annot)
            if not annot_type: annot_type = ast.PrimitiveType("_error_")
        final_type: Optional[ast.Type] = None
        if annot_type:
            if not self.check_type_compatibility(annot_type, rhs_type_maybe_literal, node.value):
                self.add_error(f"Tipo valor ({self.type_to_string(rhs_type_maybe_literal)}) incompatível com anotação ({self.type_to_string(annot_type)}) para 'mut {var_name}'", node.value) # Erro no valor
            final_type = annot_type
        else:
            resolved_rhs_type = self.get_concrete_type(rhs_type_maybe_literal)
            if resolved_rhs_type is None or isinstance(resolved_rhs_type, UnitType):
                 self.add_error(f"Não é possível inferir tipo ou usar '()' para 'mut {var_name}'. Use uma anotação de tipo.", node.value); final_type = ast.PrimitiveType("_error_")
            elif isinstance(resolved_rhs_type, ast.ArrayType) and isinstance(resolved_rhs_type.element_type, ast.PrimitiveType) and resolved_rhs_type.element_type.name == "_empty_array_":
                 self.add_error(f"Não é possível inferir o tipo de `[]` para 'mut {var_name}'. Use uma anotação de tipo (ex: `mut arr: [i32; 0] = [];`).", node.value); final_type = ast.PrimitiveType("_error_")
            else: final_type = resolved_rhs_type
        setattr(node, 'declared_type', final_type)
        if not self.declare_local(var_name, node): self.add_error(f"Variável 'mut {var_name}' já declarada neste escopo.", node.name)
        return None

    def visit_Assignment(self, node: ast.Assignment):
        lvalue_info = self.visit_lvalue(node.target) # allow_immutable_ref é False por padrão
        if isinstance(node.target, ast.Underscore): self.visit(node.value); return None
        if lvalue_info is None: return None
        target_type, is_assignable = lvalue_info
        if not is_assignable: self.add_error(f"Não é possível atribuir a um L-Value não modificável.", node.target) # Erro no alvo
        rhs_type_maybe_literal = self.visit(node.value)
        if rhs_type_maybe_literal is None: return None
        if not self.check_type_compatibility(target_type, rhs_type_maybe_literal, node.value):
            self.add_error(f"Tipo do valor ({self.type_to_string(rhs_type_maybe_literal)}) incompatível com L-Value ({self.type_to_string(target_type)}) na atribuição.", node.value) # Erro no valor
        return None

    def visit_ExpressionStatement(self, node: ast.ExpressionStatement):
        self.visit(node.expression)
        return None

    def visit_ReturnStmt(self, node: ast.ReturnStmt):
        expected_return_type = self.current_function_return_type
        func_name_ctx = f" na função '{self.current_function_name}'" if self.current_function_name else ""
        if expected_return_type is None: self.add_error(f"Comando 'return' fora de uma função.", node); return None
        actual_return_type: ast.Type
        if node.value:
            value_type_maybe_literal = self.visit(node.value)
            if value_type_maybe_literal is None: actual_return_type = ast.PrimitiveType("_error_")
            else: actual_return_type = value_type_maybe_literal
        else: actual_return_type = ast.UnitType()
        if not self.check_type_compatibility(expected_return_type, actual_return_type, node.value or node):
             self.add_error(f"Tipo retornado ({self.type_to_string(actual_return_type)}) incompatível com tipo de retorno esperado ({self.type_to_string(expected_return_type)}){func_name_ctx}.", node.value or node)
        return None

    def visit_IfStmt(self, node: ast.IfStmt):
        cond_type = self.visit(node.condition)
        bool_type = ast.PrimitiveType("bool")
        if cond_type and not self.check_type_compatibility(bool_type, cond_type, node.condition):
            self.add_error(f"Condição do 'if' deve ser do tipo 'bool', mas é '{self.type_to_string(cond_type)}'", node.condition)
        self.enter_scope()
        for stmt in node.then_block: self.visit(stmt)
        self.exit_scope()
        if node.else_block:
            self.enter_scope()
            if isinstance(node.else_block, ast.IfStmt): self.visit(node.else_block)
            elif isinstance(node.else_block, list):
                 for stmt in node.else_block: self.visit(stmt)
            self.exit_scope()
        return None

    def visit_WhileStmt(self, node: ast.WhileStmt):
        cond_type = self.visit(node.condition)
        bool_type = ast.PrimitiveType("bool")
        if cond_type and not self.check_type_compatibility(bool_type, cond_type, node.condition):
            self.add_error(f"Condição do 'while' deve ser 'bool', mas é '{self.type_to_string(cond_type)}'", node.condition)
        self.current_loop_level += 1
        self.enter_scope()
        for stmt in node.body: self.visit(stmt)
        self.exit_scope()
        self.current_loop_level -= 1
        return None

    def visit_LoopStmt(self, node: ast.LoopStmt):
        self.current_loop_level += 1
        self.enter_scope()
        for stmt in node.body: self.visit(stmt)
        self.exit_scope()
        self.current_loop_level -= 1
        return None

    def visit_BreakStmt(self, node: ast.BreakStmt):
        if self.current_loop_level == 0: self.add_error("'break' fora de um loop.", node)
        return None
    def visit_ContinueStmt(self, node: ast.ContinueStmt):
        if self.current_loop_level == 0: self.add_error("'continue' fora de um loop.", node)
        return None

    def visit_MemBlock(self, node: ast.MemBlock): # Modificado para não criar escopo
        outer_mem_block_state = self.is_in_mem_block
        self.is_in_mem_block = True
        
        # Não chama enter_scope/exit_scope
        for stmt in node.body:
            self.visit(stmt) 
            
        self.is_in_mem_block = outer_mem_block_state
        return None
        
    def visit_EMemBlock(self, node: ast.EMemBlock): # <--- NOVO MÉTODO
        outer_mem_block_state = self.is_in_mem_block
        self.is_in_mem_block = True
        
        self.enter_scope() # CRIA NOVO ESCOPO
        for stmt in node.body:
            self.visit(stmt) # Visita statements no novo escopo
        self.exit_scope()  # SAI DO ESCOPO
        
        self.is_in_mem_block = outer_mem_block_state
        return None

    def visit_IntegerLiteral(self, node: ast.IntegerLiteral) -> Optional[ast.Type]:
        return ast.LiteralIntegerType(value=node.value, default_type_name='i32')
    def visit_StringLiteral(self, node: ast.StringLiteral) -> Optional[ast.Type]:
        return ast.PointerType(pointee_type=ast.PrimitiveType('char'), is_mutable=False)
    def visit_ByteStringLiteral(self, node: ast.ByteStringLiteral) -> Optional[ast.Type]:
        return ast.SliceType(element_type=ast.PrimitiveType('u8'), is_mutable=False)
    def visit_BooleanLiteral(self, node: ast.BooleanLiteral) -> Optional[ast.Type]:
        return ast.PrimitiveType('bool')
    def visit_CharLiteral(self, node: ast.CharLiteral) -> Optional[ast.Type]:
        return ast.PrimitiveType('char')

    def visit_Identifier(self, node: ast.Identifier) -> Optional[ast.Type]:
        name = node.name
        symbol_node = self.lookup_symbol_node(name)
        if symbol_node is None: self.add_error(f"Identificador '{name}' não definido.", node); return ast.PrimitiveType("_error_")
        resolved_type: Optional[ast.Type] = None
        if isinstance(symbol_node, (ast.LetBinding, ast.MutBinding)):
            resolved_type = getattr(symbol_node, 'declared_type', None)
        elif isinstance(symbol_node, ast.Parameter):
             resolved_type = getattr(symbol_node, 'resolved_type', None)
        elif isinstance(symbol_node, ast.ConstDef):
             resolved_type = getattr(symbol_node, 'resolved_type', self._resolve_type(symbol_node.type_annot))
        elif isinstance(symbol_node, (ast.FunctionDef, ast.FunctionDecl)):
             param_types = [getattr(p, 'resolved_type', ast.PrimitiveType("_error_")) for p in symbol_node.params]
             ret_type = getattr(symbol_node, 'resolved_return_type', ast.PrimitiveType("_error_"))
             is_vararg = getattr(symbol_node, 'is_var_arg_resolved', False)
             resolved_type = ast.FunctionType(param_types=param_types, return_type=ret_type, is_var_arg=is_vararg)
        elif isinstance(symbol_node, (ast.StructDef, ast.EnumDef)):
             self.add_error(f"Uso do nome de tipo '{name}' como valor não é permitido.", node); return ast.PrimitiveType("_error_")
        else: self.add_error(f"Identificador '{name}' refere-se a um símbolo inesperado: {type(symbol_node).__name__}", node); return ast.PrimitiveType("_error_")
        if not resolved_type: return ast.PrimitiveType("_error_")
        setattr(node, 'definition_node', symbol_node) # Anota o nó de definição para lvalue
        return resolved_type

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Optional[ast.Type]:
         op = node.op
         if op == '&' or op == '&mut':
             if isinstance(node.operand, ast.ArrayLiteral) and not node.operand.elements:
                 return ast.SliceType(element_type=ast.UnitType(), is_mutable=(op == '&mut'))
             else:
                 is_mut_ref = (op == '&mut')
                 # Para &LValue, o LValue pode ser imutável. Para &mut LValue, LValue deve ser mutável.
                 lvalue_info = self.visit_lvalue(node.operand, allow_immutable_ref=(not is_mut_ref))
                 if lvalue_info:
                     target_type, is_target_mut_or_ref_mut = lvalue_info # is_target_mut_or_ref_mut indica se &mut é permitido
                     if is_mut_ref and not is_target_mut_or_ref_mut:
                         self.add_error(f"Não é possível criar uma referência mutável '&mut' para um L-Value que não seja mutável ou uma referência mutável.", node.operand)
                         return ast.PrimitiveType("_error_")
                     return ast.ReferenceType(referenced_type=target_type, is_mutable=is_mut_ref)
                 else: return ast.PrimitiveType("_error_")
         operand_type_maybe = self.visit(node.operand)
         if operand_type_maybe is None: return None
         operand_type = self.get_concrete_type(operand_type_maybe)
         if operand_type is None: return ast.PrimitiveType("_error_")
         if op == '-':
              if self.is_numeric_type(operand_type): return operand_type
              else: self.add_error(f"Operador unário '-' requer um tipo numérico, mas recebeu '{self.type_to_string(operand_type)}'.", node.operand); return ast.PrimitiveType("_error_")
         elif op == '!':
              bool_type = ast.PrimitiveType('bool')
              if self.types_are_equal(bool_type, operand_type): return bool_type
              else: self.add_error(f"Operador unário '!' requer tipo 'bool', mas recebeu '{self.type_to_string(operand_type)}'.", node.operand); return ast.PrimitiveType("_error_")
         elif op == '*':
              if not self.check_unsafe_context("Dereferência de ponteiro '*'", node): return ast.PrimitiveType("_error_")
              if isinstance(operand_type, ast.PointerType): return operand_type.pointee_type
              elif isinstance(operand_type, ast.ReferenceType): return operand_type.referenced_type
              else: self.add_error(f"Não é possível dereferenciar o tipo '{self.type_to_string(operand_type)}' com '*'.", node.operand); return ast.PrimitiveType("_error_")
         elif op == '~':
              if self.is_integer_type(operand_type): return operand_type
              else: self.add_error(f"Operador unário '~' requer um tipo inteiro, mas recebeu '{self.type_to_string(operand_type)}'.", node.operand); return ast.PrimitiveType("_error_")
         else: self.add_error(f"Operador unário desconhecido: '{op}'", node); return ast.PrimitiveType("_error_")

    def visit_BinaryOp(self, node: ast.BinaryOp) -> Optional[ast.Type]:
        op = node.op
        left_type_maybe = self.visit(node.left); right_type_maybe = self.visit(node.right)
        if left_type_maybe is None or right_type_maybe is None: return None
        left_concrete = self.get_concrete_type(left_type_maybe)
        right_concrete = self.get_concrete_type(right_type_maybe)
        if left_concrete is None or right_concrete is None: return ast.PrimitiveType("_error_")
        bool_type = ast.PrimitiveType('bool')
        if op in ('+', '-', '*', '/', '%', '&', '|', '^', '<<', '>>'):
            is_bitwise_or_shift = op in ('&', '|', '^', '<<', '>>')
            req_int = is_bitwise_or_shift or op == '%'
            if req_int:
                if not (self.is_integer_type(left_concrete) and self.is_integer_type(right_concrete)):
                     self.add_error(f"Operador binário '{op}' requer operandos inteiros. Recebeu '{self.type_to_string(left_type_maybe)}' e '{self.type_to_string(right_type_maybe)}'.", node); return ast.PrimitiveType("_error_")
            else:
                if not (self.is_numeric_type(left_concrete) and self.is_numeric_type(right_concrete)):
                     self.add_error(f"Operador binário '{op}' requer operandos numéricos. Recebeu '{self.type_to_string(left_type_maybe)}' e '{self.type_to_string(right_type_maybe)}'.", node); return ast.PrimitiveType("_error_")
            if self.check_type_compatibility(left_concrete, right_type_maybe, node.right): return left_concrete
            elif self.check_type_compatibility(right_concrete, left_type_maybe, node.left): return right_concrete
            else: self.add_error(f"Tipos incompatíveis para operador '{op}': '{self.type_to_string(left_type_maybe)}' e '{self.type_to_string(right_type_maybe)}'.", node); return ast.PrimitiveType("_error_")
        elif op in ('==', '!=', '<', '>', '<=', '>='):
             if self.check_type_compatibility(left_concrete, right_type_maybe, node.right) or \
                self.check_type_compatibility(right_concrete, left_type_maybe, node.left):
                 return bool_type
             else: self.add_error(f"Não é possível comparar tipos incompatíveis: '{self.type_to_string(left_type_maybe)}' e '{self.type_to_string(right_type_maybe)}' com '{op}'.", node); return ast.PrimitiveType("_error_")
        elif op in ('&&', '||'):
            if self.check_type_compatibility(bool_type, left_type_maybe, node.left) and \
               self.check_type_compatibility(bool_type, right_type_maybe, node.right):
                return bool_type
            else: self.add_error(f"Operador lógico '{op}' requer operandos 'bool'. Recebeu '{self.type_to_string(left_type_maybe)}' e '{self.type_to_string(right_type_maybe)}'.", node); return ast.PrimitiveType("_error_")
        else: self.add_error(f"Operador binário desconhecido: '{op}'", node); return ast.PrimitiveType("_error_")

    def visit_FieldAccess(self, node: ast.FieldAccess) -> Optional[ast.Type]:
        field_name = node.field.name
        obj_type_maybe = self.visit(node.obj)
        if obj_type_maybe is None: return None
        base_type_for_field_access = obj_type_maybe
        if isinstance(obj_type_maybe, ast.PointerType):
            if not self.check_unsafe_context(f"Acesso a campo via ponteiro bruto ('{field_name}')", node): return ast.PrimitiveType("_error_")
            base_type_for_field_access = obj_type_maybe.pointee_type
        elif isinstance(obj_type_maybe, ast.ReferenceType):
            base_type_for_field_access = obj_type_maybe.referenced_type
        resolved_base_type = self._resolve_type(base_type_for_field_access)
        if not resolved_base_type:
            self.add_error(f"Tipo base '{self.type_to_string(base_type_for_field_access)}' para acesso a campo é desconhecido ou inválido.", node.obj)
            return ast.PrimitiveType("_error_")
        setattr(node.obj, 'resolved_base_type_for_field_access', resolved_base_type) # Anota para lvalue
        if isinstance(resolved_base_type, ast.CustomType):
            struct_name = resolved_base_type.name.name
            struct_def_node = self.struct_defs.get(struct_name)
            if not struct_def_node:
                self.add_error(f"Erro interno: Struct '{struct_name}' não encontrado na definição global.", node.obj)
                return ast.PrimitiveType("_error_")
            for field_def in struct_def_node.fields:
                if field_def.name.name == field_name:
                    return getattr(field_def, 'resolved_type', ast.PrimitiveType("_error_"))
            self.add_error(f"Struct '{struct_name}' não tem campo chamado '{field_name}'.", node.field)
            return ast.PrimitiveType("_error_")
        elif isinstance(resolved_base_type, ast.SliceType):
            if field_name == "len":
                return ast.PrimitiveType('usize')
            else:
                self.add_error(f"Tipo slice '{self.type_to_string(resolved_base_type)}' não tem campo '{field_name}'. Único campo válido é '.len'.", node.field)
                return ast.PrimitiveType("_error_")
        else:
            self.add_error(f"Acesso a campo '.' não é permitido no tipo '{self.type_to_string(resolved_base_type)}'. Esperado struct ou slice.", node.obj)
            return ast.PrimitiveType("_error_")

    def visit_IndexAccess(self, node: ast.IndexAccess) -> Optional[ast.Type]:
        collection_type_maybe = self.visit(node.array); index_type_maybe = self.visit(node.index)
        if collection_type_maybe is None or index_type_maybe is None: return None
        resolved_index_type = self.get_concrete_type(index_type_maybe)
        if not self.is_integer_type(resolved_index_type):
            self.add_error(f"Índice para acesso '[]' deve ser um tipo inteiro, mas é '{self.type_to_string(resolved_index_type)}'.", node.index)
        resolved_collection_type = self.get_concrete_type(collection_type_maybe)
        element_type: Optional[ast.Type] = None
        if isinstance(resolved_collection_type, ast.ArrayType):
            element_type = resolved_collection_type.element_type
        elif isinstance(resolved_collection_type, ast.SliceType):
            element_type = resolved_collection_type.element_type
        elif isinstance(resolved_collection_type, ast.PointerType):
            if not self.check_unsafe_context("Indexação de ponteiro bruto", node): return ast.PrimitiveType("_error_")
            element_type = resolved_collection_type.pointee_type
        else:
            self.add_error(f"Não é possível indexar o tipo '{self.type_to_string(resolved_collection_type)}' com '[]'.", node.array)
            return ast.PrimitiveType("_error_")
        resolved_element_type = self._resolve_type(element_type)
        if resolved_element_type is None:
            self.add_error(f"Erro interno: tipo do elemento para indexação não pôde ser resolvido.", node.array)
            return ast.PrimitiveType("_error_")
        return resolved_element_type

    def visit_CastExpr(self, node: ast.CastExpr) -> Optional[ast.Type]:
        source_type_maybe = self.visit(node.expr)
        target_type = self._resolve_type(node.target_type)
        if source_type_maybe is None or target_type is None: return ast.PrimitiveType("_error_")
        if self.validate_cast(source_type_maybe, target_type, node):
            return target_type
        else:
            return ast.PrimitiveType("_error_")

    def validate_cast(self, from_type_maybe_literal: ast.Type, to_type: ast.Type, node: ast.CastExpr) -> bool:
        from_concrete = self.get_concrete_type(from_type_maybe_literal)
        to_concrete = self.get_concrete_type(to_type)
        if not from_concrete or not to_concrete: return False
        is_unsafe_cast = False; valid_cast = False
        if self.is_numeric_type(from_concrete) and self.is_numeric_type(to_concrete): valid_cast = True
        elif isinstance(from_concrete, ast.PointerType) and isinstance(to_concrete, ast.PointerType): valid_cast = True; is_unsafe_cast = True
        elif self.is_integer_type(from_concrete) and isinstance(to_concrete, ast.PointerType): valid_cast = True; is_unsafe_cast = True
        elif isinstance(from_concrete, ast.PointerType) and self.is_integer_type(to_concrete): valid_cast = True; is_unsafe_cast = True
        elif isinstance(from_concrete, ast.PrimitiveType) and from_concrete.name == 'bool' and self.is_integer_type(to_concrete): valid_cast = True
        elif self.is_integer_type(from_concrete) and isinstance(to_concrete, ast.PrimitiveType) and to_concrete.name == 'bool': valid_cast = True
        elif isinstance(from_concrete, ast.PrimitiveType) and isinstance(to_concrete, ast.PrimitiveType) and \
             ((from_concrete.name == 'u8' and to_concrete.name == 'char') or (from_concrete.name == 'char' and to_concrete.name == 'u8')):
            valid_cast = True
        elif isinstance(from_concrete, ast.CustomType) and from_concrete.name.name in self.enum_defs and self.is_integer_type(to_concrete):
            valid_cast = True
        if not valid_cast:
              self.add_error(f"Cast inválido de '{self.type_to_string(from_concrete)}' para '{self.type_to_string(to_concrete)}'.", node)
              return False
        if is_unsafe_cast and not self.check_unsafe_context(f"Cast inseguro de '{self.type_to_string(from_concrete)}' para '{self.type_to_string(to_concrete)}'", node):
             return False
        return True

    def visit_FunctionCall(self, node: ast.FunctionCall) -> Optional[ast.Type]:
        callee_type_maybe = self.visit(node.callee)
        if callee_type_maybe is None: return None
        callee_type = self.get_concrete_type(callee_type_maybe)
        if not isinstance(callee_type, ast.FunctionType):
            self.add_error(f"Expressão não é chamável. Esperado um tipo função (func(...)), mas recebeu '{self.type_to_string(callee_type)}'.", node.callee)
            return ast.PrimitiveType("_error_")
        if isinstance(node.callee, ast.Identifier):
            callee_node = self.lookup_symbol_node(node.callee.name)
            if isinstance(callee_node, ast.FunctionDecl) and getattr(callee_node, 'is_extern', False):
                 if not self.check_unsafe_context(f"Chamada para função externa (FFI) '{node.callee.name}'", node): pass
        arg_types_maybe = [self.visit(arg) for arg in node.args]
        if None in arg_types_maybe: return ast.PrimitiveType("_error_")
        expected_param_types = callee_type.param_types
        is_vararg_func = callee_type.is_var_arg
        num_expected_named_params = len(expected_param_types)
        num_provided_args = len(arg_types_maybe)
        error_msg_count = None
        if is_vararg_func:
            if num_provided_args < num_expected_named_params:
                error_msg_count = f"Função varargs espera pelo menos {num_expected_named_params} argumentos nomeados, mas recebeu {num_provided_args}."
        elif num_provided_args != num_expected_named_params:
            error_msg_count = f"Função espera {num_expected_named_params} argumentos, mas recebeu {num_provided_args}."
        if error_msg_count: self.add_error(error_msg_count, node)
        max_args_to_check_type = min(num_expected_named_params, num_provided_args)
        for i in range(max_args_to_check_type):
            expected_param_type = expected_param_types[i]
            provided_arg_type_maybe = arg_types_maybe[i]
            arg_node_for_error = node.args[i]
            if not self.check_type_compatibility(expected_param_type, provided_arg_type_maybe, arg_node_for_error):
                self.add_error(f"Tipo do argumento {i+1} ({self.type_to_string(provided_arg_type_maybe)}) é incompatível com o tipo do parâmetro esperado ({self.type_to_string(expected_param_type)}).", arg_node_for_error)
        return self._resolve_type(callee_type.return_type)

    def visit_ArrayLiteral(self, node: ast.ArrayLiteral) -> Optional[ast.Type]:
        if not node.elements: return ast.ArrayType(element_type=ast.PrimitiveType("_empty_array_"), size=ast.IntegerLiteral(value=0))
        element_types_maybe = [self.visit(el) for el in node.elements]
        if None in element_types_maybe: return ast.PrimitiveType("_error_")
        first_element_type_maybe = element_types_maybe[0]
        resolved_first_type = self.get_concrete_type(first_element_type_maybe)
        if resolved_first_type is None: return ast.PrimitiveType("_error_")
        for i, other_element_type_maybe in enumerate(element_types_maybe[1:], start=1):
            if not self.check_type_compatibility(resolved_first_type, other_element_type_maybe, node.elements[i]):
                 self.add_error(f"Tipo do elemento {i} ({self.type_to_string(other_element_type_maybe)}) no array literal é incompatível com o tipo do primeiro elemento ({self.type_to_string(resolved_first_type)}).", node.elements[i])
                 return ast.PrimitiveType("_error_")
        array_size_node = ast.IntegerLiteral(value=len(node.elements))
        return ast.ArrayType(element_type=resolved_first_type, size=array_size_node)

    def visit_StructLiteral(self, node: ast.StructLiteral) -> Optional[ast.Type]:
        type_name = node.type_name.name
        # DEBUG: Início de visit_StructLiteral
        # print(f"DEBUG SemAna: visit_StructLiteral para tipo '{type_name}' (Node: {node!r})")

        struct_def_node = self.struct_defs.get(type_name)
        if not struct_def_node:
            self.add_error(f"Tipo '{type_name}' não é um struct definido.", node.type_name)
            return ast.PrimitiveType("_error_")

        # DEBUG: Definição do Struct e seus campos definidos
        defined_fields_map = {}
        # print(f"  DEBUG SemAna: StructDef '{type_name}' fields (AST):")
        for f_def in struct_def_node.fields:
            field_def_name = f_def.name.name
            resolved_type = getattr(f_def, 'resolved_type', ast.PrimitiveType("_UNRESOLVED_IN_STRUCT_DEF_"))
            defined_fields_map[field_def_name] = resolved_type
            print(f"    - Defined Field: '{field_def_name}', Resolved Type: {self.type_to_string(resolved_type)}")
        
        # print(f"  DEBUG SemAna: defined_fields_map = { {k: self.type_to_string(v) for k,v in defined_fields_map.items()} }")


        provided_field_names = set()
        has_errors = False

        # print(f"  DEBUG SemAna: Processando campos fornecidos no literal:")
        for field_literal_node in node.fields: # Renomeado para evitar conflito com 'field' de struct_def
            field_name_in_literal = field_literal_node.name.name
            print(f"    - Literal Field: '{field_name_in_literal}' (Node: {field_literal_node.name!r})")

            if field_name_in_literal in provided_field_names:
                self.add_error(f"Campo '{field_name_in_literal}' duplicado no literal de struct '{type_name}'.", field_literal_node.name)
                has_errors = True
                continue
            provided_field_names.add(field_name_in_literal)

            if field_name_in_literal not in defined_fields_map:
                self.add_error(f"Struct '{type_name}' não possui campo chamado '{field_name_in_literal}'.", field_literal_node.name)
                has_errors = True
                continue # Pula para o próximo campo do literal se este não existe na definição

            # Se o campo existe na definição, processa seu valor
            value_type_maybe = self.visit(field_literal_node.value) # Visita o valor do campo do literal
            if value_type_maybe is None:
                print(f"      WARN SemAna: Valor para campo '{field_name_in_literal}' não pôde ser determinado (visit retornou None).")
                has_errors = True
                continue

            expected_field_type = defined_fields_map[field_name_in_literal]
            print(f"      - Checking compatibility for field '{field_name_in_literal}': Value type = {self.type_to_string(value_type_maybe)}, Expected type = {self.type_to_string(expected_field_type)}")
            if not self.check_type_compatibility(expected_field_type, value_type_maybe, field_literal_node.value):
                 self.add_error(f"Tipo do valor para o campo '{field_name_in_literal}' ({self.type_to_string(value_type_maybe)}) é incompatível com o tipo esperado do campo ({self.type_to_string(expected_field_type)}) no literal de '{type_name}'.", field_literal_node.value)
                 has_errors = True

        # Verifica campos faltando APÓS processar todos os campos fornecidos
        missing_fields = set(defined_fields_map.keys()) - provided_field_names
        if missing_fields:
            # print(f"  DEBUG SemAna: Campos faltando: {missing_fields}")
            self.add_error(f"Campos faltando no literal de struct '{type_name}': {', '.join(sorted(list(missing_fields)))}.", node)
            has_errors = True

        if has_errors:
            # print(f"  DEBUG SemAna: Erros encontrados em StructLiteral '{type_name}'. Retornando _error_.")
            return ast.PrimitiveType("_error_")
        else:
            # print(f"  DEBUG SemAna: StructLiteral '{type_name}' OK. Retornando CustomType.")
            return ast.CustomType(name=node.type_name) # Retorna o tipo CustomType do struct

    def visit_ArrayRepeatExpr(self, node: ast.ArrayRepeatExpr) -> Optional[ast.Type]:
        value_type_maybe = self.visit(node.value); size_type_maybe = self.visit(node.size)
        if value_type_maybe is None or size_type_maybe is None: return None
        resolved_value_type = self.get_concrete_type(value_type_maybe)
        resolved_size_type = self.get_concrete_type(size_type_maybe)
        if resolved_value_type is None or resolved_size_type is None: return ast.PrimitiveType("_error_")
        if not self.is_integer_type(resolved_size_type):
            self.add_error(f"Tamanho N na expressão de array '[valor; N]' deve ser um inteiro, mas é '{self.type_to_string(resolved_size_type)}'.", node.size)
        if not self.is_constant_expression(node.size):
            self.add_error(f"Tamanho N na expressão de array '[valor; N]' deve ser uma expressão constante.", node.size)
            return ast.PrimitiveType("_error_")
        return ast.ArrayType(element_type=resolved_value_type, size=node.size)

    def visit_NamespaceAccess(self, node: ast.NamespaceAccess) -> Optional[ast.Type]:
         namespace_name = node.namespace.name; item_name = node.item.name
         enum_def_node = self.enum_defs.get(namespace_name)
         if not enum_def_node:
             self.add_error(f"Namespace ou tipo '{namespace_name}' não definido ou não é um enum.", node.namespace)
             return ast.PrimitiveType("_error_")
         if namespace_name not in self.enum_variant_values or item_name not in self.enum_variant_values[namespace_name]:
              self.add_error(f"Enum '{namespace_name}' não possui variante chamada '{item_name}'.", node.item)
              return ast.PrimitiveType("_error_")
         setattr(node, 'resolved_variant_value', self.enum_variant_values[namespace_name][item_name])
         setattr(node, 'resolved_enum_def_node', enum_def_node)
         return ast.CustomType(name=ast.Identifier(name=namespace_name))

    def visit_Underscore(self, node: ast.Underscore) -> Optional[ast.Type]:
         self.add_error("Underscore '_' não pode ser usado como um valor em uma expressão.", node)
         return None

    def _resolve_type(self, type_node: Optional[ast.Type]) -> Optional[ast.Type]:
        if type_node is None: return None
        if isinstance(type_node, (ast.PrimitiveType, ast.UnitType, ast.LiteralIntegerType)):
            if isinstance(type_node, ast.PrimitiveType) and type_node.name != "_error_" and type_node.name not in self.llvm_types:
                 self.add_error(f"Tipo primitivo desconhecido: '{type_node.name}'", type_node); return ast.PrimitiveType("_error_")
            return type_node
        if isinstance(type_node, ast.PointerType):
            resolved_pointee = self._resolve_type(type_node.pointee_type)
            if resolved_pointee is None or (isinstance(resolved_pointee, PrimitiveType) and resolved_pointee.name == "_error_"): return ast.PrimitiveType("_error_")
            return ast.PointerType(pointee_type=resolved_pointee, is_mutable=type_node.is_mutable)
        if isinstance(type_node, ast.ReferenceType):
            resolved_referenced = self._resolve_type(type_node.referenced_type)
            if resolved_referenced is None or (isinstance(resolved_referenced, PrimitiveType) and resolved_referenced.name == "_error_"): return ast.PrimitiveType("_error_")
            return ast.ReferenceType(referenced_type=resolved_referenced, is_mutable=type_node.is_mutable)
        if isinstance(type_node, ast.ArrayType):
            resolved_element = self._resolve_type(type_node.element_type)
            if resolved_element is None or (isinstance(resolved_element, PrimitiveType) and resolved_element.name == "_error_"): return ast.PrimitiveType("_error_")
            return ast.ArrayType(element_type=resolved_element, size=type_node.size)
        if isinstance(type_node, ast.SliceType):
            resolved_element = self._resolve_type(type_node.element_type)
            if resolved_element is None or (isinstance(resolved_element, PrimitiveType) and resolved_element.name == "_error_"): return ast.PrimitiveType("_error_")
            return ast.SliceType(element_type=resolved_element, is_mutable=type_node.is_mutable)
        if isinstance(type_node, ast.FunctionType):
             resolved_params = [self._resolve_type(p) for p in type_node.param_types]
             # Checa se algum parâmetro não pôde ser resolvido
             if any(rp is None or (isinstance(rp, PrimitiveType) and rp.name=="_error_") for rp in resolved_params): return ast.PrimitiveType("_error_")
             # Força os tipos None/erro a serem _error_ para consistência
             safe_resolved_params = [rp if rp else ast.PrimitiveType("_error_") for rp in resolved_params]

             resolved_ret = self._resolve_type(type_node.return_type)
             if resolved_ret is None or (isinstance(resolved_ret, PrimitiveType) and resolved_ret.name=="_error_"): return ast.PrimitiveType("_error_")
             safe_resolved_ret = resolved_ret if resolved_ret else ast.PrimitiveType("_error_")

             return ast.FunctionType(param_types=safe_resolved_params, return_type=safe_resolved_ret, is_var_arg=type_node.is_var_arg)
        if isinstance(type_node, ast.CustomType):
            type_name = type_node.name.name
            if type_name in self.struct_defs or type_name in self.enum_defs:
                return type_node
            else: self.add_error(f"Tipo customizado '{type_name}' não definido.", type_node.name); return ast.PrimitiveType("_error_")
        self.add_error(f"Tipo AST não suportado na resolução: {type(type_node).__name__}", type_node)
        return ast.PrimitiveType("_error_")

    def get_concrete_type(self, type_node: Optional[ast.Type]) -> Optional[ast.Type]:
        resolved = self._resolve_type(type_node)
        if isinstance(resolved, ast.LiteralIntegerType):
            return ast.PrimitiveType(name=resolved.default_type_name)
        return resolved

    def types_are_equal(self, type1_maybe_literal: Optional[ast.Type], type2_maybe_literal: Optional[ast.Type]) -> bool:
        t1 = self.get_concrete_type(type1_maybe_literal)
        t2 = self.get_concrete_type(type2_maybe_literal)
        if t1 is None or t2 is None: return False
        if isinstance(t1, PrimitiveType) and t1.name == "_error_": return True # Erro é compatível com tudo para evitar cascata
        if isinstance(t2, PrimitiveType) and t2.name == "_error_": return True
        if type(t1) is not type(t2): return False
        if isinstance(t1, ast.PrimitiveType): return t1.name == t2.name
        if isinstance(t1, ast.UnitType): return True
        if isinstance(t1, ast.CustomType): return t1.name.name == t2.name.name
        if isinstance(t1, ast.PointerType): return t1.is_mutable == t2.is_mutable and self.types_are_equal(t1.pointee_type, t2.pointee_type)
        if isinstance(t1, ast.ReferenceType): return t1.is_mutable == t2.is_mutable and self.types_are_equal(t1.referenced_type, t2.referenced_type)
        if isinstance(t1, ast.SliceType): return t1.is_mutable == t2.is_mutable and self.types_are_equal(t1.element_type, t2.element_type)
        if isinstance(t1, ast.ArrayType):
            elements_equal = self.types_are_equal(t1.element_type, t2.element_type)
            size1_val = getattr(t1.size, 'value', None) if isinstance(t1.size, ast.IntegerLiteral) else None
            size2_val = getattr(t2.size, 'value', None) if isinstance(t2.size, ast.IntegerLiteral) else None
            # Para igualdade de tipos array, os tamanhos DEVEM ser conhecidos e iguais em tempo de compilação.
            # Se um dos tamanhos não for literal, não podemos dizer que são iguais aqui.
            if size1_val is None or size2_val is None or size1_val != size2_val:
                return False # Tamanhos diferentes ou não conhecidos como literais
            return elements_equal
        if isinstance(t1, ast.FunctionType):
            if len(t1.param_types) != len(t2.param_types) or \
               t1.is_var_arg != t2.is_var_arg or \
               not self.types_are_equal(t1.return_type, t2.return_type):
                return False
            for p1_type, p2_type in zip(t1.param_types, t2.param_types):
                if not self.types_are_equal(p1_type, p2_type): return False
            return True
        return False

    def check_type_compatibility(self, target_type: Optional[ast.Type], value_type_maybe_literal: Optional[ast.Type], value_node: Optional[ast.Node] = None) -> bool:
        target_resolved = self.get_concrete_type(target_type)
        if target_resolved is None or value_type_maybe_literal is None: return False
        if isinstance(target_resolved, PrimitiveType) and target_resolved.name == "_error_": return True
        if isinstance(value_type_maybe_literal, PrimitiveType) and value_type_maybe_literal.name == "_error_": return True

        if isinstance(value_type_maybe_literal, ast.LiteralIntegerType):
            literal_val = value_type_maybe_literal.value
            if isinstance(target_resolved, ast.PrimitiveType) and self.is_integer_type(target_resolved):
                return self.check_literal_fits_integer_type(literal_val, target_resolved.name, value_node)
            else: return False
        is_value_empty_array_literal = (isinstance(value_type_maybe_literal, ast.ArrayType) and isinstance(value_type_maybe_literal.element_type, ast.PrimitiveType) and value_type_maybe_literal.element_type.name == "_empty_array_")
        is_value_empty_slice_placeholder = (isinstance(value_type_maybe_literal, ast.SliceType) and isinstance(value_type_maybe_literal.element_type, ast.UnitType))

        if is_value_empty_array_literal or is_value_empty_slice_placeholder:
            if isinstance(target_resolved, ast.SliceType):
                 # Verifica mutabilidade: &[T] pode receber de &[] ou &mut []
                 # &mut [T] só pode receber de &mut []
                 # A mutabilidade do valor é dada por value_type_maybe_literal.is_mutable
                 # A mutabilidade do target é dada por target_resolved.is_mutable
                 if target_resolved.is_mutable and not value_type_maybe_literal.is_mutable: # Ex: let s: &mut [i32] = &[]; (value é &[], target é &mut)
                      return False
                 return True
            elif is_value_empty_array_literal and isinstance(target_resolved, ast.ArrayType) and isinstance(target_resolved.size, ast.IntegerLiteral) and target_resolved.size.value == 0:
                 return True
            elif is_value_empty_slice_placeholder and isinstance(target_resolved, ast.ReferenceType) and \
                 isinstance(target_resolved.referenced_type, ast.ArrayType) and \
                 isinstance(target_resolved.referenced_type.size, ast.IntegerLiteral) and \
                 target_resolved.referenced_type.size.value == 0:
                 # Verifica mutabilidade da referência e do placeholder
                 if target_resolved.is_mutable and not value_type_maybe_literal.is_mutable:
                      return False
                 return True
            else: return False
        value_resolved = self.get_concrete_type(value_type_maybe_literal)
        if value_resolved is None: return False
        if self.types_are_equal(target_resolved, value_resolved): return True
        if isinstance(target_resolved, ast.ReferenceType) and not target_resolved.is_mutable and \
           isinstance(value_resolved, ast.ReferenceType) and value_resolved.is_mutable and \
           self.types_are_equal(target_resolved.referenced_type, value_resolved.referenced_type):
            return True
        if isinstance(target_resolved, ast.PointerType) and not target_resolved.is_mutable and \
           isinstance(value_resolved, ast.PointerType) and value_resolved.is_mutable and \
           self.types_are_equal(target_resolved.pointee_type, value_resolved.pointee_type):
            return True
        if isinstance(target_resolved, ast.SliceType) and \
           isinstance(value_resolved, ast.ReferenceType) and isinstance(value_resolved.referenced_type, ast.ArrayType) and \
           target_resolved.is_mutable == value_resolved.is_mutable and \
           self.types_are_equal(target_resolved.element_type, value_resolved.referenced_type.element_type):
            return True
        if isinstance(target_resolved, ast.SliceType) and not target_resolved.is_mutable and \
           isinstance(value_resolved, ast.ArrayType) and \
           self.types_are_equal(target_resolved.element_type, value_resolved.element_type):
            return True
        return False

    def check_literal_fits_integer_type(self, value: int, type_name: str, node: Optional[ast.Node]) -> bool:
        limits = { 'i8': (-128, 127), 'u8': (0, 255), 'i16': (-32768, 32767), 'u16': (0, 65535),
                   'i32': (-2147483648, 2147483647), 'u32': (0, 4294967295),
                   'i64': (-9223372036854775808, 9223372036854775807), 'u64': (0, 18446744073709551615),
                   'isize': (-2**63, 2**63-1), 'usize': (0, 2**64-1),
                   'int': (-2**31, 2**31-1), 'uint': (0, 2**32-1) }
        if type_name in limits:
            min_val, max_val = limits[type_name]
            if not (min_val <= value <= max_val):
                self.add_error(f"Literal inteiro '{value}' fora dos limites ({min_val}..{max_val}) para o tipo '{type_name}'.", node)
                return False
            return True
        elif type_name == "_error_": return True
        else: self.add_error(f"Erro interno: check_literal_fits_integer_type chamado com tipo não inteiro '{type_name}'.", node); return False

    def is_numeric_type(self, type_node: Optional[ast.Type]) -> bool:
         resolved_type = self.get_concrete_type(type_node)
         return isinstance(resolved_type, ast.PrimitiveType) and resolved_type.name in self.numeric_types
    def is_integer_type(self, type_node: Optional[ast.Type]) -> bool:
         resolved_type = self.get_concrete_type(type_node)
         return isinstance(resolved_type, ast.PrimitiveType) and resolved_type.name in self.integer_types

    def evaluate_constant_int_expr(self, node: ast.Expression, visiting: Optional[Set[int]] = None) -> Optional[int]: # <--- Tipo do Set mudou para int
        if visiting is None: visiting = set()
        
        node_id = id(node) # <--- Obter ID do nó
        if node_id in visiting: # <--- Verificar ID no set
            self.add_error("Detectada dependência cíclica em expressão constante.", node)
            return None
        visiting.add(node_id) # <--- Adicionar ID ao set

        result: Optional[int] = None
        try: # Usar try/finally para garantir remoção do ID
            if isinstance(node, ast.IntegerLiteral):
                result = node.value
            elif isinstance(node, ast.Identifier):
                symbol = self.lookup_symbol_node(node.name)
                if isinstance(symbol, ast.ConstDef):
                    # Passa o mesmo set 'visiting' na chamada recursiva
                    result = self.evaluate_constant_int_expr(symbol.value, visiting) 
                # ... (resto da lógica do Identifier) ...
            elif isinstance(node, ast.BinaryOp):
                # Passa o mesmo set 'visiting' nas chamadas recursivas
                left_val = self.evaluate_constant_int_expr(node.left, visiting)
                right_val = self.evaluate_constant_int_expr(node.right, visiting)
                # ... (resto da lógica do BinaryOp) ...
            elif isinstance(node, ast.UnaryOp):
                 # Passa o mesmo set 'visiting' na chamada recursiva
                operand_val = self.evaluate_constant_int_expr(node.operand, visiting)
                # ... (resto da lógica do UnaryOp) ...
            elif isinstance(node, ast.CastExpr):
                 # Passa o mesmo set 'visiting' na chamada recursiva
                inner_val = self.evaluate_constant_int_expr(node.expr, visiting)
                # ... (resto da lógica do CastExpr) ...
            elif isinstance(node, ast.NamespaceAccess):
                 # ... (lógica do NamespaceAccess, não recursiva em termos de avaliação constante) ...
                 enum_name = node.namespace.name
                 variant_name = node.item.name
                 if enum_name in self.enum_variant_values and variant_name in self.enum_variant_values[enum_name]:
                     result = self.enum_variant_values[enum_name][variant_name]
                 else:
                      self.add_error(f"Variante de enum constante '{enum_name}::{variant_name}' não encontrada ou inválida.", node)
            else:
                 self.add_error(f"Expressão do tipo '{type(node).__name__}' não pode ser avaliada como um inteiro constante.", node)
        finally:
             visiting.remove(node_id) # <--- Remover ID do set

        return result
    
    def is_constant_expression(self, node: ast.Expression, visiting: Optional[Set[int]] = None) -> bool: # <--- Tipo do Set mudou para int
        if visiting is None: visiting = set()

        node_id = id(node) # <--- Obter ID do nó
        if node_id in visiting: # <--- Verificar ID no set
            return False 
        visiting.add(node_id) # <--- Adicionar ID ao set

        result = False 
        try: 
            if isinstance(node, (ast.IntegerLiteral, ast.BooleanLiteral, ast.CharLiteral, ast.StringLiteral, ast.ByteStringLiteral)):
                result = True
            elif isinstance(node, ast.Identifier):
                symbol_node = self.lookup_symbol_node(node.name)
                if isinstance(symbol_node, ast.ConstDef):
                    # Passa o mesmo set 'visiting' na chamada recursiva
                    result = self.is_constant_expression(symbol_node.value, visiting) 
                else: result = False 
            elif isinstance(node, ast.NamespaceAccess):
                # ... (lógica como antes, não recursiva) ...
                 ns_node = self.lookup_symbol_node(node.namespace.name)
                 if isinstance(ns_node, ast.EnumDef):
                     result = any(v.name.name == node.item.name for v in ns_node.variants)
                 else: result = False
            elif isinstance(node, ast.ArrayLiteral):
                 # Passa o mesmo set 'visiting' nas chamadas recursivas
                 result = all(self.is_constant_expression(el, visiting) for el in node.elements)
            elif isinstance(node, ast.StructLiteral):
                 # ... (verifica campos) ...
                 # Passa o mesmo set 'visiting' nas chamadas recursivas
                 struct_def_node = self.lookup_symbol_node(node.type_name.name)
                 if not isinstance(struct_def_node, ast.StructDef): result = False
                 else:
                     defined_field_names = {f.name.name for f in struct_def_node.fields}
                     literal_field_names = {f.name.name for f in node.fields}
                     if defined_field_names != literal_field_names: result = False
                     else: result = all(self.is_constant_expression(f.value, visiting) for f in node.fields)
            elif isinstance(node, ast.ArrayRepeatExpr):
                 # Passa o mesmo set 'visiting' nas chamadas recursivas
                 result = self.is_constant_expression(node.value, visiting) and self.is_constant_expression(node.size, visiting)
            elif isinstance(node, ast.CastExpr):
                 # Passa o mesmo set 'visiting' na chamada recursiva
                result = self.is_constant_expression(node.expr, visiting)
            elif isinstance(node, ast.UnaryOp):
                if node.op in ('!', '-', '~'): 
                     # Passa o mesmo set 'visiting' na chamada recursiva
                    result = self.is_constant_expression(node.operand, visiting)
                else: result = False 
            elif isinstance(node, ast.BinaryOp):
                if node.op in ('+', '-', '*', '/', '%', '&', '|', '^', '<<', '>>', '==', '!=', '<', '>', '<=', '>='):
                     # Passa o mesmo set 'visiting' nas chamadas recursivas
                     result = self.is_constant_expression(node.left, visiting) and self.is_constant_expression(node.right, visiting)
                elif node.op in ('&&', '||'):
                      # Passa o mesmo set 'visiting' nas chamadas recursivas
                     result = self.is_constant_expression(node.left, visiting) and self.is_constant_expression(node.right, visiting)
                else: result = False
            elif isinstance(node, ast.FieldAccess):
                 # Passa o mesmo set 'visiting' na chamada recursiva
                result = self.is_constant_expression(node.obj, visiting)
            elif isinstance(node, ast.IndexAccess):
                 # Passa o mesmo set 'visiting' nas chamadas recursivas
                result = self.is_constant_expression(node.array, visiting) and self.is_constant_expression(node.index, visiting)
            else: result = False
        finally:
             visiting.remove(node_id) # <--- Remover ID do set

        return result

    # <=== DEFINIÇÃO CORRIGIDA AQUI ===>
    def visit_lvalue(self, node: ast.Expression, allow_immutable_ref: bool = False) -> Optional[Tuple[ast.Type, bool]]:
        lvalue_type: Optional[ast.Type] = None
        is_assignable: bool = False # Se o L-Value pode estar no lado esquerdo de uma atribuição '='
        can_form_mut_ref: bool = False # Se podemos fazer &mut LValue
        error_msg: Optional[str] = None

        if isinstance(node, ast.Identifier):
            symbol_node = getattr(node, 'definition_node', self.lookup_symbol_node(node.name)) # Usa anotação se existir
            if not symbol_node: self.add_error(f"Identificador '{node.name}' não definido.", node); return None

            if isinstance(symbol_node, ast.MutBinding):
                lvalue_type = getattr(symbol_node, 'declared_type', None)
                is_assignable = True; can_form_mut_ref = True
            elif isinstance(symbol_node, ast.LetBinding):
                lvalue_type = getattr(symbol_node, 'declared_type', None)
                is_assignable = False; can_form_mut_ref = False
                error_msg = f"Não é possível modificar variável imutável 'let {node.name}'."
            elif isinstance(symbol_node, ast.Parameter):
                param_base_type = getattr(symbol_node, 'resolved_type', None)
                lvalue_type = param_base_type # Tipo do L-Value é o tipo do parâmetro
                if isinstance(param_base_type, ast.ReferenceType) and param_base_type.is_mutable:
                    is_assignable = True; can_form_mut_ref = True
                    lvalue_type = param_base_type.referenced_type # L-Value é T de &mut T
                else: # Parâmetro por valor ou &T
                    is_assignable = False; can_form_mut_ref = False
                    error_msg = f"Não é possível modificar parâmetro imutável '{node.name}' (tipo: {self.type_to_string(param_base_type)})."
            elif isinstance(symbol_node, ast.ConstDef):
                lvalue_type = getattr(symbol_node, 'resolved_type', None); is_assignable = False; can_form_mut_ref = False
                error_msg = f"Não é possível usar constante '{node.name}' como L-Value modificável."
            else: error_msg = f"Identificador '{node.name}' não pode ser usado como L-Value."; return None
            if not lvalue_type: self.add_error(f"Erro interno: tipo de '{node.name}' não determinado.", node); return None

        elif isinstance(node, ast.FieldAccess):
            # Tipo do objeto base (ex: S em obj.field, ou T em (&obj).field)
            # O `visit_FieldAccess` já resolve o tipo do campo, que é o tipo do L-Value.
            # A mutabilidade depende da base.
            field_type_from_access = self.visit_FieldAccess(node) # Visita normal para obter o tipo do campo
            if field_type_from_access is None or (isinstance(field_type_from_access, PrimitiveType) and field_type_from_access.name == "_error_"):
                return None # Erro já reportado por visit_FieldAccess

            lvalue_type = field_type_from_access

            # Para determinar a mutabilidade, precisamos do tipo "real" do objeto que contém o campo.
            # Ex: se obj é `&mut S`, tipo real é `S`. Se obj é `mut s: S`, tipo real é `S`.
            # Usamos a anotação 'resolved_base_type_for_field_access' de visit_FieldAccess
            obj_base_type = getattr(node.obj, 'resolved_base_type_for_field_access', None)
            # E também o tipo original do nó obj (antes de desreferenciar)
            obj_original_type = getattr(node.obj, 'atom_type', None)

            # Se o campo for '.len' de um slice, não é atribuível.
            if isinstance(obj_base_type, ast.SliceType) and node.field.name == "len":
                is_assignable = False; can_form_mut_ref = False
                error_msg = "Não é possível atribuir ao campo '.len' de um slice."
            elif isinstance(obj_base_type, ast.CustomType): # É um struct
                # L-Value de obj.field (ex: (s.f1).f2)
                # allow_immutable_ref=True permite obter L-Value para leitura de campos de base imutável
                base_obj_lvalue_info = self.visit_lvalue(node.obj, allow_immutable_ref=True)
                if base_obj_lvalue_info is None: return None
                _, base_obj_can_form_mut_ref_or_is_directly_mut = base_obj_lvalue_info

                # É atribuível/pode formar &mut se a base puder
                is_assignable = base_obj_can_form_mut_ref_or_is_directly_mut
                can_form_mut_ref = base_obj_can_form_mut_ref_or_is_directly_mut
                if not is_assignable:
                    error_msg = f"Não é possível modificar o campo '{node.field.name}' pois a base não é modificável."
            else: # Não é struct nem slice (erro já deve ter sido pego por visit_FieldAccess)
                return None


        elif isinstance(node, ast.IndexAccess):
            element_type_from_access = self.visit_IndexAccess(node)
            if element_type_from_access is None or (isinstance(element_type_from_access, PrimitiveType) and element_type_from_access.name == "_error_"):
                return None
            lvalue_type = element_type_from_access

            collection_original_type = getattr(node.array, 'atom_type', None)
            collection_concrete_type = self.get_concrete_type(collection_original_type)

            if isinstance(collection_concrete_type, ast.ArrayType):
                # Para `arr[i]`, mutabilidade depende de `arr` ser `mut` ou `&mut [T;N]`
                # Precisamos checar a "mutabilidade" da própria `node.array`
                array_lvalue_info = self.visit_lvalue(node.array, allow_immutable_ref=True)
                if array_lvalue_info is None: return None
                _, array_can_form_mut_ref_or_is_directly_mut = array_lvalue_info
                is_assignable = array_can_form_mut_ref_or_is_directly_mut
                can_form_mut_ref = array_can_form_mut_ref_or_is_directly_mut
                if not is_assignable: error_msg = "Não é possível modificar elemento de array imutável."

            elif isinstance(collection_concrete_type, ast.SliceType):
                is_assignable = collection_concrete_type.is_mutable # &mut [T]
                can_form_mut_ref = collection_concrete_type.is_mutable
                if not is_assignable: error_msg = "Não é possível modificar elemento de slice imutável '&[T]'."

            elif isinstance(collection_concrete_type, ast.PointerType):
                 is_assignable = collection_concrete_type.is_mutable # *mut T
                 can_form_mut_ref = collection_concrete_type.is_mutable
                 if not is_assignable: error_msg = "Não é possível modificar elemento via ponteiro '*const T'."
            else: # Não deve acontecer se visit_IndexAccess passou
                return None


        elif isinstance(node, ast.UnaryOp) and node.op == '*':
            operand_type_resolved = self.get_concrete_type(self.visit(node.operand))
            if isinstance(operand_type_resolved, ast.PointerType):
                if not self.check_unsafe_context("L-Value de dereferência de ponteiro bruto '*'", node): return None
                lvalue_type = operand_type_resolved.pointee_type
                is_assignable = operand_type_resolved.is_mutable
                can_form_mut_ref = operand_type_resolved.is_mutable
                if not is_assignable: error_msg = "Não é possível atribuir via dereferência de ponteiro '*const'."
            elif isinstance(operand_type_resolved, ast.ReferenceType):
                lvalue_type = operand_type_resolved.referenced_type
                is_assignable = operand_type_resolved.is_mutable
                can_form_mut_ref = operand_type_resolved.is_mutable
                if not is_assignable: error_msg = "Não é possível atribuir via dereferência de referência imutável '&'."
            else: error_msg = f"Não é possível usar dereferência '*' como L-Value para o tipo '{self.type_to_string(operand_type_resolved)}'."; return None
        else:
            error_msg = f"Expressão do tipo '{type(node).__name__}' não pode ser usada como L-Value."; return None

        # Se `allow_immutable_ref` é True, não emitimos erro se `can_form_mut_ref` for False.
        # Isso é usado por `visit_UnaryOp` para `&LValue`.
        # Para atribuição (`a = b`), `allow_immutable_ref` é False, então erro será emitido se `is_assignable` for False.
        if not allow_immutable_ref and not is_assignable: # Para atribuição
            self.add_error(error_msg or "L-Value não é modificável para atribuição.", node)
        elif allow_immutable_ref and not can_form_mut_ref: # Para &mut LValue
            # Se allow_immutable_ref é True, significa que estamos tentando pegar &LValue ou &mut LValue.
            # Se can_form_mut_ref é False, então &mut LValue não é permitido.
            # O erro específico de &mut LValue é tratado em visit_UnaryOp.
            # Aqui, apenas retornamos a informação.
            pass


        if lvalue_type is None:
            self.add_error(f"Erro interno: tipo do L-Value não pôde ser determinado.", node)
            return None
            
        # Retorna o tipo do L-Value e se ele pode ser usado para formar &mut ou se é diretamente mutável
        return (lvalue_type, can_form_mut_ref)


def analyze_semantics(program_node: ast.Program) -> List[str]:
    analyzer = SemanticAnalyzer()
    try:
        return analyzer.analyze(program_node)
    except Exception as e:
        print(f"ERRO INTERNO IRRECUPERÁVEL DO ANALISADOR SEMÂNTICO: {e}")
        traceback.print_exc()
        analyzer.add_error(f"Erro interno irrecuperável durante análise: {e}")
        return analyzer.errors
