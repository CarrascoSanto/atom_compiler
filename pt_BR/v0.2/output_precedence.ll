; ModuleID = "atom_module"
target triple = "x86_64-unknown-linux-gnu"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"

%"Vec2" = type {i32, i32}
%"MyData" = type {i32}
%"Slice.\22MyData\22" = type {%"MyData"*, i64}
%"Slice.i32" = type {i32*, i64}
%"Entity" = type {%"Vec2"*, %"Vec2", i8*, [4 x i8], %"Slice.\22Entity\22"}
%"Slice.\22Entity\22" = type {%"Entity"*, i64}
%"Slice.i8" = type {i8*, i64}
declare void @"atom_panic_bounds_check"(i64 %".1", i64 %".2")

declare void @"atom_do_bounds_check"(i64 %".1", i64 %".2")

define i64 @"process_slice"(%"Slice.\22MyData\22" %"data_slice.1", %"Slice.i32" %"empty_slice.1")
{
entry:
  %"data_slice.addr" = alloca %"Slice.\22MyData\22"
  store %"Slice.\22MyData\22" %"data_slice.1", %"Slice.\22MyData\22"* %"data_slice.addr"
  %"empty_slice.addr" = alloca %"Slice.i32"
  store %"Slice.i32" %"empty_slice.1", %"Slice.i32"* %"empty_slice.addr"
  %"slice.len.ptr" = getelementptr inbounds %"Slice.\22MyData\22", %"Slice.\22MyData\22"* %"data_slice.addr", i32 0, i32 1
  %"len.load" = load i64, i64* %"slice.len.ptr"
  %"len1.addr" = alloca i64
  store i64 %"len.load", i64* %"len1.addr"
  %"slice.len.ptr.1" = getelementptr inbounds %"Slice.i32", %"Slice.i32"* %"empty_slice.addr", i32 0, i32 1
  %"len.load.1" = load i64, i64* %"slice.len.ptr.1"
  %"len2.addr" = alloca i64
  store i64 %"len.load.1", i64* %"len2.addr"
  %"len1" = load i64, i64* %"len1.addr"
  %".8" = zext i32 0 to i64
  %"len1.1" = load i64, i64* %"len1.addr"
  %".9" = zext i32 0 to i64
  %"ucmp" = icmp ugt i64 %"len1", %".8"
  br i1 %"ucmp", label %"if.then", label %"if.end"
if.then:
  %"idx.zext" = zext i32 0 to i64
  %"slice.len.ptr.bc" = getelementptr %"Slice.\22MyData\22", %"Slice.\22MyData\22"* %"data_slice.addr", i32 0, i32 1
  %"slice.len.bc" = load i64, i64* %"slice.len.ptr.bc"
  call void @"atom_do_bounds_check"(i64 %"idx.zext", i64 %"slice.len.bc")
  %"slice.data.ptr.addr" = getelementptr inbounds %"Slice.\22MyData\22", %"Slice.\22MyData\22"* %"data_slice.addr", i32 0, i32 0
  %"slice.data.ptr" = load %"MyData"*, %"MyData"** %"slice.data.ptr.addr"
  %"slice.elem.ptr" = getelementptr inbounds %"MyData", %"MyData"* %"slice.data.ptr", i64 %"idx.zext"
  %"id.ptr" = getelementptr inbounds %"MyData", %"MyData"* %"slice.elem.ptr", i32 0, i32 0
  %"id.load" = load i32, i32* %"id.ptr"
  %"first_id.addr" = alloca i32
  store i32 %"id.load", i32* %"first_id.addr"
  %"first_id" = load i32, i32* %"first_id.addr"
  %"calltmp" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([14 x i8], [14 x i8]* @".str.0", i32 0, i32 0), i32 %"first_id")
  br label %"if.end"
if.end:
  %"len1.2" = load i64, i64* %"len1.addr"
  %"len2" = load i64, i64* %"len2.addr"
  %"addtmp" = add i64 %"len1.2", %"len2"
  ret i64 %"addtmp"
}

@"SIZE" = internal constant i64 5
@"ORIGIN" = internal constant %"Vec2" {i32 0, i32 0}
declare i32 @"printf"(i8* %"_extern_param0", ...)

declare i32 @"puts"(i8* %"_extern_param0")

define i1 @"my_callback_func"(i32 %"n.1")
{
entry:
  %"n.addr" = alloca i32
  store i32 %"n.1", i32* %"n.addr"
  %"n.2" = load i32, i32* %"n.addr"
  %"n.3" = load i32, i32* %"n.addr"
  %"scmp" = icmp sgt i32 %"n.2", 0
  br i1 %"scmp", label %"if.then", label %"if.else"
if.then:
  ret i1 1
if.else:
  ret i1 0
}

define void @"update_entity"(%"Entity"* %"e.1", i32 %"dt_scale_factor.1")
{
entry:
  %"e.addr" = alloca %"Entity"*
  store %"Entity"* %"e.1", %"Entity"** %"e.addr"
  %"dt_scale_factor.addr" = alloca i32
  store i32 %"dt_scale_factor.1", i32* %"dt_scale_factor.addr"
  %"e.load" = load %"Entity"*, %"Entity"** %"e.addr"
  %"vel.ptr" = getelementptr inbounds %"Entity", %"Entity"* %"e.load", i32 0, i32 1
  %"x.ptr" = getelementptr inbounds %"Vec2", %"Vec2"* %"vel.ptr", i32 0, i32 0
  %"x.load" = load i32, i32* %"x.ptr"
  %"dt_scale_factor.2" = load i32, i32* %"dt_scale_factor.addr"
  %"multmp" = mul i32 %"x.load", %"dt_scale_factor.2"
  %".6" = sdiv i32 %"multmp", 256
  %"move_x.addr" = alloca i32
  store i32 %".6", i32* %"move_x.addr"
  %"e.load.1" = load %"Entity"*, %"Entity"** %"e.addr"
  %"pos.ptr" = getelementptr inbounds %"Entity", %"Entity"* %"e.load.1", i32 0, i32 0
  %"ptr.load" = load %"Vec2"*, %"Vec2"** %"pos.ptr"
  %"x.ptr.1" = getelementptr inbounds %"Vec2", %"Vec2"* %"ptr.load", i32 0, i32 0
  %"x.load.1" = load i32, i32* %"x.ptr.1"
  %"_.addr" = alloca i32
  store i32 %"x.load.1", i32* %"_.addr"
  ret void
}

define void @"test_mem_no_scope"()
{
entry:
  %"x.addr" = alloca i32
  store i32 10, i32* %"x.addr"
  %"x" = load i32, i32* %"x.addr"
  %"addtmp" = add i32 %"x", 5
  %"y.addr" = alloca i32
  store i32 %"addtmp", i32* %"y.addr"
  %"y" = load i32, i32* %"y.addr"
  %"z.addr" = alloca i32
  store i32 %"y", i32* %"z.addr"
  ret void
}

define void @"test_e_mem_with_scope"()
{
entry:
  %"x.addr" = alloca i32
  store i32 10, i32* %"x.addr"
  %"result.addr" = alloca i32
  store i32 0, i32* %"result.addr"
  %"x" = load i32, i32* %"x.addr"
  %"addtmp" = add i32 %"x", 5
  %"y_internal.addr" = alloca i32
  store i32 %"addtmp", i32* %"y_internal.addr"
  %"y_internal" = load i32, i32* %"y_internal.addr"
  %"multmp" = mul i32 %"y_internal", 2
  store i32 %"multmp", i32* %"result.addr"
  %"result" = load i32, i32* %"result.addr"
  %"final_val.addr" = alloca i32
  store i32 %"result", i32* %"final_val.addr"
  ret void
}

define void @"main"()
{
entry:
  %"multmp" = mul i32 100, 2
  %"addtmp" = add i32 %"multmp", 50
  %"score.addr" = alloca i32
  store i32 %"addtmp", i32* %"score.addr"
  %"Vec2.x" = insertvalue %"Vec2" zeroinitializer, i32 10, 0
  %"Vec2.y" = insertvalue %"Vec2" %"Vec2.x", i32 20, 1
  %"current_pos.addr" = alloca %"Vec2"
  store %"Vec2" %"Vec2.y", %"Vec2"* %"current_pos.addr"
  %"static_msg.addr" = alloca i8*
  store i8* getelementptr ([12 x i8], [12 x i8]* @".str.1", i32 0, i32 0), i8** %"static_msg.addr"
  %"another_msg.addr" = alloca i8*
  store i8* getelementptr ([19 x i8], [19 x i8]* @".str.2", i32 0, i32 0), i8** %"another_msg.addr"
  %"Vec2.x.1" = insertvalue %"Vec2" zeroinitializer, i32 1, 0
  %"Vec2.y.1" = insertvalue %"Vec2" %"Vec2.x.1", i32 1, 1
  %".6" = sub i32 0, 1
  %"Vec2.x.2" = insertvalue %"Vec2" zeroinitializer, i32 %".6", 0
  %".7" = sub i32 0, 1
  %"Vec2.y.2" = insertvalue %"Vec2" %"Vec2.x.2", i32 %".7", 1
  %"arr.elem0" = insertvalue [3 x %"Vec2"] zeroinitializer, %"Vec2" %"Vec2.y.1", 0
  %"arr.elem1" = insertvalue [3 x %"Vec2"] %"arr.elem0", %"Vec2" {i32 0, i32 0}, 1
  %"arr.elem2" = insertvalue [3 x %"Vec2"] %"arr.elem1", %"Vec2" %"Vec2.y.2", 2
  %"points.addr" = alloca [3 x %"Vec2"]
  store [3 x %"Vec2"] %"arr.elem2", [3 x %"Vec2"]* %"points.addr"
  %".9" = insertvalue %"Slice.\22Entity\22" zeroinitializer, %"Entity"* null, 0
  %".10" = insertvalue %"Slice.\22Entity\22" %".9", i64 0, 1
  %"empty_entities.addr" = alloca %"Slice.\22Entity\22"
  store %"Slice.\22Entity\22" %".10", %"Slice.\22Entity\22"* %"empty_entities.addr"
  %".12" = trunc i32 1 to i8
  %"repeat.elem0" = insertvalue [4 x i8] zeroinitializer, i8 %".12", 0
  %"repeat.elem1" = insertvalue [4 x i8] %"repeat.elem0", i8 %".12", 1
  %"repeat.elem2" = insertvalue [4 x i8] %"repeat.elem1", i8 %".12", 2
  %"repeat.elem3" = insertvalue [4 x i8] %"repeat.elem2", i8 %".12", 3
  %"default_sprites.addr" = alloca [4 x i8]
  store [4 x i8] %"repeat.elem3", [4 x i8]* %"default_sprites.addr"
  %"score" = load i32, i32* %"score.addr"
  %".14" = sdiv i32 %"score", 2
  %"next_score.addr" = alloca i32
  store i32 %".14", i32* %"next_score.addr"
  %"x.ptr" = getelementptr inbounds %"Vec2", %"Vec2"* %"current_pos.addr", i32 0, i32 0
  %"x.load" = load i32, i32* %"x.ptr"
  %"x.ptr.1" = getelementptr inbounds %"Vec2", %"Vec2"* @"ORIGIN", i32 0, i32 0
  %"x.load.1" = load i32, i32* %"x.ptr.1"
  %"x.ptr.2" = getelementptr inbounds %"Vec2", %"Vec2"* %"current_pos.addr", i32 0, i32 0
  %"x.load.2" = load i32, i32* %"x.ptr.2"
  %"x.ptr.3" = getelementptr inbounds %"Vec2", %"Vec2"* @"ORIGIN", i32 0, i32 0
  %"x.load.3" = load i32, i32* %"x.ptr.3"
  %"scmp" = icmp eq i32 %"x.load", %"x.load.1"
  br i1 %"scmp", label %"op.&&.eval_b", label %"op.&&.merge"
"op.&&.eval_b":
  %"y.ptr" = getelementptr inbounds %"Vec2", %"Vec2"* %"current_pos.addr", i32 0, i32 1
  %"y.load" = load i32, i32* %"y.ptr"
  %"y.ptr.1" = getelementptr inbounds %"Vec2", %"Vec2"* @"ORIGIN", i32 0, i32 1
  %"y.load.1" = load i32, i32* %"y.ptr.1"
  %"y.ptr.2" = getelementptr inbounds %"Vec2", %"Vec2"* %"current_pos.addr", i32 0, i32 1
  %"y.load.2" = load i32, i32* %"y.ptr.2"
  %"y.ptr.3" = getelementptr inbounds %"Vec2", %"Vec2"* @"ORIGIN", i32 0, i32 1
  %"y.load.3" = load i32, i32* %"y.ptr.3"
  %"scmp.1" = icmp eq i32 %"y.load", %"y.load.1"
  br label %"op.&&.merge"
"op.&&.merge":
  %"op.&&.result" = phi  i1 [0, %"entry"], [%"scmp.1", %"op.&&.eval_b"]
  %"is_zero.addr" = alloca i1
  store i1 %"op.&&.result", i1* %"is_zero.addr"
  %"idx.zext" = zext i32 0 to i64
  call void @"atom_do_bounds_check"(i64 %"idx.zext", i64 3)
  %"arr.elem.ptr" = getelementptr inbounds [3 x %"Vec2"], [3 x %"Vec2"]* %"points.addr", i32 0, i64 %"idx.zext"
  %"x.ptr.4" = getelementptr inbounds %"Vec2", %"Vec2"* %"arr.elem.ptr", i32 0, i32 0
  %"x.load.4" = load i32, i32* %"x.ptr.4"
  %"first_pt_x.addr" = alloca i32
  store i32 %"x.load.4", i32* %"first_pt_x.addr"
  %"another_msg" = load i8*, i8** %"another_msg.addr"
  %"temp_ptr.addr" = alloca i8*
  store i8* %"another_msg", i8** %"temp_ptr.addr"
  %"temp_ptr" = load i8*, i8** %"temp_ptr.addr"
  %"calltmp" = call i32 @"puts"(i8* %"temp_ptr")
  %"calltmp.1" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([10 x i8], [10 x i8]* @".str.3", i32 0, i32 0), i32 123)
  %"Entity.pos" = insertvalue %"Entity" zeroinitializer, %"Vec2"* %"current_pos.addr", 0
  %"multmp.1" = mul i32 5, 256
  %"Vec2.x.3" = insertvalue %"Vec2" zeroinitializer, i32 %"multmp.1", 0
  %"Vec2.y.3" = insertvalue %"Vec2" %"Vec2.x.3", i32 0, 1
  %"Entity.vel" = insertvalue %"Entity" %"Entity.pos", %"Vec2" %"Vec2.y.3", 1
  %"static_msg" = load i8*, i8** %"static_msg.addr"
  %"Entity.tag" = insertvalue %"Entity" %"Entity.vel", i8* %"static_msg", 2
  %"default_sprites" = load [4 x i8], [4 x i8]* %"default_sprites.addr"
  %"Entity.sprite_ids" = insertvalue %"Entity" %"Entity.tag", [4 x i8] %"default_sprites", 3
  %"empty_entities" = load %"Slice.\22Entity\22", %"Slice.\22Entity\22"* %"empty_entities.addr"
  %"Entity.neighbors" = insertvalue %"Entity" %"Entity.sprite_ids", %"Slice.\22Entity\22" %"empty_entities", 4
  %"player_entity.addr" = alloca %"Entity"
  store %"Entity" %"Entity.neighbors", %"Entity"* %"player_entity.addr"
  %"is_zero" = load i1, i1* %"is_zero.addr"
  br i1 %"is_zero", label %"op.||.merge", label %"op.||.eval_b"
"op.||.eval_b":
  %"first_pt_x" = load i32, i32* %"first_pt_x.addr"
  %"first_pt_x.1" = load i32, i32* %"first_pt_x.addr"
  %"scmp.2" = icmp slt i32 %"first_pt_x", 0
  br label %"op.||.merge"
"op.||.merge":
  %"op.||.result" = phi  i1 [1, %"op.&&.merge"], [%"scmp.2", %"op.||.eval_b"]
  br i1 %"op.||.result", label %"if.then", label %"if.else"
if.then:
  br label %"if.end"
if.else:
  %"i.addr" = alloca i32
  store i32 0, i32* %"i.addr"
  br label %"while.cond"
if.end:
  %"flags.addr" = alloca i8
  store i8 202, i8* %"flags.addr"
  %"flags" = load i8, i8* %"flags.addr"
  %".35" = trunc i32 15 to i8
  %".36" = and i8 %"flags", %".35"
  %"masked.addr" = alloca i8
  store i8 %".36", i8* %"masked.addr"
  %"masked" = load i8, i8* %"masked.addr"
  %".38" = trunc i32 2 to i8
  %".39" = shl i8 %"masked", %".38"
  %"shifted.addr" = alloca i8
  store i8 %".39", i8* %"shifted.addr"
  %"flags.1" = load i8, i8* %"flags.addr"
  %".41" = xor i8 %"flags.1", -1
  %"inverted.addr" = alloca i8
  store i8 %".41", i8* %"inverted.addr"
  %"shifted" = load i8, i8* %"shifted.addr"
  %".43" = trunc i32 1 to i8
  %".44" = or i8 %"shifted", %".43"
  %"combined.addr" = alloca i8
  store i8 %".44", i8* %"combined.addr"
  %"combined" = load i8, i8* %"combined.addr"
  %"masked.1" = load i8, i8* %"masked.addr"
  %".46" = xor i8 %"combined", %"masked.1"
  %"xor_test.addr" = alloca i8
  store i8 %".46", i8* %"xor_test.addr"
  %"cb.addr" = alloca i1 (i32)*
  store i1 (i32)* @"my_callback_func", i1 (i32)** %"cb.addr"
  %"cb" = load i1 (i32)*, i1 (i32)** %"cb.addr"
  %"calltmp.2" = call i1 %"cb"(i32 10)
  %"is_pos.addr" = alloca i1
  store i1 %"calltmp.2", i1* %"is_pos.addr"
  %"cb.1" = load i1 (i32)*, i1 (i32)** %"cb.addr"
  %".50" = sub i32 0, 5
  %"calltmp.3" = call i1 %"cb.1"(i32 %".50")
  %"is_neg.addr" = alloca i1
  store i1 %"calltmp.3", i1* %"is_neg.addr"
  %"current_state.addr" = alloca i32
  store i32 1, i32* %"current_state.addr"
  %"next_state.addr" = alloca i32
  store i32 0, i32* %"next_state.addr"
  %"current_state" = load i32, i32* %"current_state.addr"
  %"next_state" = load i32, i32* %"next_state.addr"
  %"calltmp.4" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([35 x i8], [35 x i8]* @".str.4", i32 0, i32 0), i32 %"current_state", i32 %"next_state")
  %"current_state.1" = load i32, i32* %"current_state.addr"
  %"current_state.2" = load i32, i32* %"current_state.addr"
  %"scmp.4" = icmp eq i32 %"current_state.1", 1
  br i1 %"scmp.4", label %"if.then.1", label %"if.end.1"
while.cond:
  %"i" = load i32, i32* %"i.addr"
  %"i.1" = load i32, i32* %"i.addr"
  %"scmp.3" = icmp slt i32 %"i", 3
  br i1 %"scmp.3", label %"while.body", label %"while.end"
while.body:
  %"i.2" = load i32, i32* %"i.addr"
  %"addtmp.1" = add i32 %"i.2", 1
  %"dummy.addr" = alloca i32
  store i32 %"addtmp.1", i32* %"dummy.addr"
  %"dummy" = load i32, i32* %"dummy.addr"
  store i32 %"dummy", i32* %"i.addr"
  br label %"while.cond"
while.end:
  br label %"if.end"
if.then.1:
  %"calltmp.5" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([20 x i8], [20 x i8]* @".str.5", i32 0, i32 0))
  br label %"if.end.1"
if.end.1:
  %".56" = insertvalue %"Slice.i8" zeroinitializer, i8* getelementptr ([7 x i8], [7 x i8]* @".bstr.0", i32 0, i32 0), 0
  %".57" = insertvalue %"Slice.i8" %".56", i64 7, 1
  %"my_bstr.addr" = alloca %"Slice.i8"
  store %"Slice.i8" %".57", %"Slice.i8"* %"my_bstr.addr"
  %"k_loop.addr" = alloca i32
  store i32 0, i32* %"k_loop.addr"
  br label %"loop.header"
loop.header:
  %"k_loop" = load i32, i32* %"k_loop.addr"
  %"addtmp.2" = add i32 %"k_loop", 1
  store i32 %"addtmp.2", i32* %"k_loop.addr"
  %"k_loop.1" = load i32, i32* %"k_loop.addr"
  %"k_loop.2" = load i32, i32* %"k_loop.addr"
  %"scmp.5" = icmp eq i32 %"k_loop.1", 2
  br i1 %"scmp.5", label %"if.then.2", label %"if.end.2"
loop.end:
  %"k_loop.6" = load i32, i32* %"k_loop.addr"
  %"calltmp.7" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([32 x i8], [32 x i8]* @".str.7", i32 0, i32 0), i32 %"k_loop.6")
  %"j_while.addr" = alloca i32
  store i32 0, i32* %"j_while.addr"
  br label %"while.cond.1"
if.then.2:
  br label %"loop.header"
if.end.2:
  %"k_loop.3" = load i32, i32* %"k_loop.addr"
  %"calltmp.6" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([12 x i8], [12 x i8]* @".str.6", i32 0, i32 0), i32 %"k_loop.3")
  %"k_loop.4" = load i32, i32* %"k_loop.addr"
  %"k_loop.5" = load i32, i32* %"k_loop.addr"
  %"scmp.6" = icmp eq i32 %"k_loop.4", 4
  br i1 %"scmp.6", label %"if.then.3", label %"if.end.3"
if.then.3:
  br label %"loop.end"
if.end.3:
  br label %"loop.header"
while.cond.1:
  %"j_while" = load i32, i32* %"j_while.addr"
  %"j_while.1" = load i32, i32* %"j_while.addr"
  %"scmp.7" = icmp slt i32 %"j_while", 5
  br i1 %"scmp.7", label %"while.body.1", label %"while.end.1"
while.body.1:
  %"j_while.2" = load i32, i32* %"j_while.addr"
  %"addtmp.3" = add i32 %"j_while.2", 1
  store i32 %"addtmp.3", i32* %"j_while.addr"
  %"j_while.3" = load i32, i32* %"j_while.addr"
  %"j_while.4" = load i32, i32* %"j_while.addr"
  %"scmp.8" = icmp eq i32 %"j_while.3", 3
  br i1 %"scmp.8", label %"if.then.4", label %"if.end.4"
while.end.1:
  %"j_while.8" = load i32, i32* %"j_while.addr"
  %"calltmp.11" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([34 x i8], [34 x i8]* @".str.11", i32 0, i32 0), i32 %"j_while.8")
  %"masked.2" = load i8, i8* %"masked.addr"
  %".76" = zext i8 %"masked.2" to i32
  %"shifted.1" = load i8, i8* %"shifted.addr"
  %".77" = zext i8 %"shifted.1" to i32
  %"combined.1" = load i8, i8* %"combined.addr"
  %".78" = zext i8 %"combined.1" to i32
  %"inverted" = load i8, i8* %"inverted.addr"
  %".79" = zext i8 %"inverted" to i32
  %"xor_test" = load i8, i8* %"xor_test.addr"
  %".80" = zext i8 %"xor_test" to i32
  %"calltmp.12" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([62 x i8], [62 x i8]* @".str.12", i32 0, i32 0), i32 %".76", i32 %".77", i32 %".78", i32 %".79", i32 %".80")
  %"is_pos" = load i1, i1* %"is_pos.addr"
  %".81" = zext i1 %"is_pos" to i32
  %"is_neg" = load i1, i1* %"is_neg.addr"
  %".82" = zext i1 %"is_neg" to i32
  %"calltmp.13" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([26 x i8], [26 x i8]* @".str.13", i32 0, i32 0), i32 %".81", i32 %".82")
  %"MyData.id" = insertvalue %"MyData" zeroinitializer, i32 10, 0
  %"d1.addr" = alloca %"MyData"
  store %"MyData" %"MyData.id", %"MyData"* %"d1.addr"
  %"MyData.id.1" = insertvalue %"MyData" zeroinitializer, i32 20, 0
  %"d2.addr" = alloca %"MyData"
  store %"MyData" %"MyData.id.1", %"MyData"* %"d2.addr"
  %"MyData.id.2" = insertvalue %"MyData" zeroinitializer, i32 30, 0
  %"d3.addr" = alloca %"MyData"
  store %"MyData" %"MyData.id.2", %"MyData"* %"d3.addr"
  %"d1" = load %"MyData", %"MyData"* %"d1.addr"
  %"d2" = load %"MyData", %"MyData"* %"d2.addr"
  %"d3" = load %"MyData", %"MyData"* %"d3.addr"
  %"arr.elem0.1" = insertvalue [3 x %"MyData"] zeroinitializer, %"MyData" %"d1", 0
  %"arr.elem1.1" = insertvalue [3 x %"MyData"] %"arr.elem0.1", %"MyData" %"d2", 1
  %"arr.elem2.1" = insertvalue [3 x %"MyData"] %"arr.elem1.1", %"MyData" %"d3", 2
  %"my_array.addr" = alloca [3 x %"MyData"]
  store [3 x %"MyData"] %"arr.elem2.1", [3 x %"MyData"]* %"my_array.addr"
  %"arraydecay.ptr" = getelementptr [3 x %"MyData"], [3 x %"MyData"]* %"my_array.addr", i32 0, i32 0
  %".87" = insertvalue %"Slice.\22MyData\22" zeroinitializer, %"MyData"* %"arraydecay.ptr", 0
  %"a_slice.sliceval" = insertvalue %"Slice.\22MyData\22" %".87", i64 3, 1
  %"a_slice.addr" = alloca %"Slice.\22MyData\22"
  store %"Slice.\22MyData\22" %"a_slice.sliceval", %"Slice.\22MyData\22"* %"a_slice.addr"
  %"a_slice" = load %"Slice.\22MyData\22", %"Slice.\22MyData\22"* %"a_slice.addr"
  %"another_slice.addr" = alloca %"Slice.\22MyData\22"
  store %"Slice.\22MyData\22" %"a_slice", %"Slice.\22MyData\22"* %"another_slice.addr"
  %".90" = insertvalue %"Slice.i32" zeroinitializer, i32* null, 0
  %".91" = insertvalue %"Slice.i32" %".90", i64 0, 1
  %"empty.addr" = alloca %"Slice.i32"
  store %"Slice.i32" %".91", %"Slice.i32"* %"empty.addr"
  %"another_slice" = load %"Slice.\22MyData\22", %"Slice.\22MyData\22"* %"another_slice.addr"
  %"empty" = load %"Slice.i32", %"Slice.i32"* %"empty.addr"
  %"calltmp.14" = call i64 @"process_slice"(%"Slice.\22MyData\22" %"another_slice", %"Slice.i32" %"empty")
  %"res.addr" = alloca i64
  store i64 %"calltmp.14", i64* %"res.addr"
  %"res" = load i64, i64* %"res.addr"
  %"calltmp.15" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([35 x i8], [35 x i8]* @".str.14", i32 0, i32 0), i64 %"res")
  %"arr.elem0.2" = insertvalue [2 x i32] zeroinitializer, i32 100, 0
  %"arr.elem1.2" = insertvalue [2 x i32] %"arr.elem0.2", i32 200, 1
  %"mut_array.addr" = alloca [2 x i32]
  store [2 x i32] %"arr.elem1.2", [2 x i32]* %"mut_array.addr"
  %"arraydecay.ptr.1" = getelementptr [2 x i32], [2 x i32]* %"mut_array.addr", i32 0, i32 0
  %".95" = insertvalue %"Slice.i32" zeroinitializer, i32* %"arraydecay.ptr.1", 0
  %"mut_s.sliceval" = insertvalue %"Slice.i32" %".95", i64 2, 1
  %"mut_s.addr" = alloca %"Slice.i32"
  store %"Slice.i32" %"mut_s.sliceval", %"Slice.i32"* %"mut_s.addr"
  %".97" = insertvalue %"Slice.i8" zeroinitializer, i8* getelementptr ([5 x i8], [5 x i8]* @".bstr.1", i32 0, i32 0), 0
  %".98" = insertvalue %"Slice.i8" %".97", i64 5, 1
  %"b_str_slice.addr" = alloca %"Slice.i8"
  store %"Slice.i8" %".98", %"Slice.i8"* %"b_str_slice.addr"
  %".100" = insertvalue %"Slice.i8" zeroinitializer, i8* getelementptr ([4 x i8], [4 x i8]* @".bstr.2", i32 0, i32 0), 0
  %".101" = insertvalue %"Slice.i8" %".100", i64 4, 1
  %"my_bytes_test.addr" = alloca %"Slice.i8"
  store %"Slice.i8" %".101", %"Slice.i8"* %"my_bytes_test.addr"
  %"calltmp.16" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([39 x i8], [39 x i8]* @".str.15", i32 0, i32 0))
  %"idx.zext.1" = zext i32 3 to i64
  %"slice.len.ptr.bc" = getelementptr %"Slice.\22MyData\22", %"Slice.\22MyData\22"* %"a_slice.addr", i32 0, i32 1
  %"slice.len.bc" = load i64, i64* %"slice.len.ptr.bc"
  call void @"atom_do_bounds_check"(i64 %"idx.zext.1", i64 %"slice.len.bc")
  %"slice.data.ptr.addr" = getelementptr inbounds %"Slice.\22MyData\22", %"Slice.\22MyData\22"* %"a_slice.addr", i32 0, i32 0
  %"slice.data.ptr" = load %"MyData"*, %"MyData"** %"slice.data.ptr.addr"
  %"slice.elem.ptr" = getelementptr inbounds %"MyData", %"MyData"* %"slice.data.ptr", i64 %"idx.zext.1"
  %"idx.load" = load %"MyData", %"MyData"* %"slice.elem.ptr"
  %"calltmp.17" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([39 x i8], [39 x i8]* @".str.16", i32 0, i32 0))
  %"idx.zext.2" = zext i32 5 to i64
  %"slice.len.ptr.bc.1" = getelementptr %"Slice.\22MyData\22", %"Slice.\22MyData\22"* %"a_slice.addr", i32 0, i32 1
  %"slice.len.bc.1" = load i64, i64* %"slice.len.ptr.bc.1"
  call void @"atom_do_bounds_check"(i64 %"idx.zext.2", i64 %"slice.len.bc.1")
  %"slice.data.ptr.addr.1" = getelementptr inbounds %"Slice.\22MyData\22", %"Slice.\22MyData\22"* %"a_slice.addr", i32 0, i32 0
  %"slice.data.ptr.1" = load %"MyData"*, %"MyData"** %"slice.data.ptr.addr.1"
  %"slice.elem.ptr.1" = getelementptr inbounds %"MyData", %"MyData"* %"slice.data.ptr.1", i64 %"idx.zext.2"
  %"idx.load.1" = load %"MyData", %"MyData"* %"slice.elem.ptr.1"
  %"calltmp.18" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([37 x i8], [37 x i8]* @".str.17", i32 0, i32 0))
  %"idx.zext.3" = zext i32 2 to i64
  %"slice.len.ptr.bc.2" = getelementptr %"Slice.i32", %"Slice.i32"* %"mut_s.addr", i32 0, i32 1
  %"slice.len.bc.2" = load i64, i64* %"slice.len.ptr.bc.2"
  call void @"atom_do_bounds_check"(i64 %"idx.zext.3", i64 %"slice.len.bc.2")
  %"slice.data.ptr.addr.2" = getelementptr inbounds %"Slice.i32", %"Slice.i32"* %"mut_s.addr", i32 0, i32 0
  %"slice.data.ptr.2" = load i32*, i32** %"slice.data.ptr.addr.2"
  %"slice.elem.ptr.2" = getelementptr inbounds i32, i32* %"slice.data.ptr.2", i64 %"idx.zext.3"
  store i32 500, i32* %"slice.elem.ptr.2"
  %"calltmp.19" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([43 x i8], [43 x i8]* @".str.18", i32 0, i32 0))
  %"idx.zext.4" = zext i32 5 to i64
  %"slice.len.ptr.bc.3" = getelementptr %"Slice.i8", %"Slice.i8"* %"b_str_slice.addr", i32 0, i32 1
  %"slice.len.bc.3" = load i64, i64* %"slice.len.ptr.bc.3"
  call void @"atom_do_bounds_check"(i64 %"idx.zext.4", i64 %"slice.len.bc.3")
  %"slice.data.ptr.addr.3" = getelementptr inbounds %"Slice.i8", %"Slice.i8"* %"b_str_slice.addr", i32 0, i32 0
  %"slice.data.ptr.3" = load i8*, i8** %"slice.data.ptr.addr.3"
  %"slice.elem.ptr.3" = getelementptr inbounds i8, i8* %"slice.data.ptr.3", i64 %"idx.zext.4"
  %"idx.load.2" = load i8, i8* %"slice.elem.ptr.3"
  %"calltmp.20" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([40 x i8], [40 x i8]* @".str.19", i32 0, i32 0))
  %"idx.zext.5" = zext i32 3 to i64
  call void @"atom_do_bounds_check"(i64 %"idx.zext.5", i64 3)
  %"arr.elem.ptr.1" = getelementptr inbounds [3 x %"MyData"], [3 x %"MyData"]* %"my_array.addr", i32 0, i64 %"idx.zext.5"
  %"idx.load.3" = load %"MyData", %"MyData"* %"arr.elem.ptr.1"
  %"calltmp.21" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([76 x i8], [76 x i8]* @".str.20", i32 0, i32 0))
  ret void
if.then.4:
  %"calltmp.8" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([22 x i8], [22 x i8]* @".str.8", i32 0, i32 0))
  br label %"while.cond.1"
if.end.4:
  %"j_while.5" = load i32, i32* %"j_while.addr"
  %"j_while.6" = load i32, i32* %"j_while.addr"
  %"scmp.9" = icmp eq i32 %"j_while.5", 5
  br i1 %"scmp.9", label %"if.then.5", label %"if.end.5"
if.then.5:
  %"calltmp.9" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([19 x i8], [19 x i8]* @".str.9", i32 0, i32 0))
  br label %"while.end.1"
if.end.5:
  %"j_while.7" = load i32, i32* %"j_while.addr"
  %"calltmp.10" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([13 x i8], [13 x i8]* @".str.10", i32 0, i32 0), i32 %"j_while.7")
  br label %"while.cond.1"
}

@".str.0" = private unnamed_addr constant [14 x i8] c"First ID: %d\0a\00"
@".str.1" = private unnamed_addr constant [12 x i8] c"Hello Atom!\00"
@".str.2" = private unnamed_addr constant [19 x i8] c"Uma linha simples.\00"
@".str.3" = private unnamed_addr constant [10 x i8] c"Hello %d\0a\00"
@".str.4" = private unnamed_addr constant [35 x i8] c"Current state: %d, Next state: %d\0a\00"
@".str.5" = private unnamed_addr constant [20 x i8] c"Entity is running!\0a\00"
@".bstr.0" = private unnamed_addr constant [7 x i8] c"Atom\01\02\03"
@".str.6" = private unnamed_addr constant [12 x i8] c"Loop k: %d\0a\00"
@".str.7" = private unnamed_addr constant [32 x i8] c"Loop finalizado com k_loop: %d\0a\00"
@".str.8" = private unnamed_addr constant [22 x i8] c"While j==3, continue\0a\00"
@".str.9" = private unnamed_addr constant [19 x i8] c"While j==5, break\0a\00"
@".str.10" = private unnamed_addr constant [13 x i8] c"While j: %d\0a\00"
@".str.11" = private unnamed_addr constant [34 x i8] c"While finalizado com j_while: %d\0a\00"
@".str.12" = private unnamed_addr constant [62 x i8] c"Masked: %u, Shifted: %u, Combined: %u, Inverted: %u, XOR: %u\0a\00"
@".str.13" = private unnamed_addr constant [26 x i8] c"Callback results: %u, %u\0a\00"
@".str.14" = private unnamed_addr constant [35 x i8] c"Total len from process_slice: %lu\0a\00"
@".bstr.1" = private unnamed_addr constant [5 x i8] c"hello"
@".bstr.2" = private unnamed_addr constant [4 x i8] c"Data"
@".str.15" = private unnamed_addr constant [39 x i8] c"Tentando acessar a_slice[3] (fora)...\0a\00"
@".str.16" = private unnamed_addr constant [39 x i8] c"Tentando acessar a_slice[5] (fora)...\0a\00"
@".str.17" = private unnamed_addr constant [37 x i8] c"Tentando acessar mut_s[2] (fora)...\0a\00"
@".str.18" = private unnamed_addr constant [43 x i8] c"Tentando acessar b_str_slice[5] (fora)...\0a\00"
@".str.19" = private unnamed_addr constant [40 x i8] c"Tentando acessar my_array[3] (fora)...\0a\00"
@".str.20" = private unnamed_addr constant [76 x i8] c"Bounds check tests conclu\c3\addos (se n\c3\a3o houve p\c3\a2nico, algo est\c3\a1 errado).\0a\00"