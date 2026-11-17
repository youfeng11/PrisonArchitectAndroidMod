/* Prison Architect Android v49 ARM. Sync the loaded object bank into the enum
 * before the original ReadMaterials call. Addresses are relative to libmain.so. */
.syntax unified
.arm
.text
.global register_object_sprites
register_object_sprites:
    push {r0, r1, r4-r8, lr}
    ldr r4, .Lapp_slot
.Lapp_pc:
    ldr r4, [pc, r4]
    ldr r4, [r4]
    cmp r4, #0
    beq .Lread_materials
    ldr r5, .Lnames_slot
.Lnames_pc:
    ldr r5, [pc, r5]
    add r4, r4, #0x400
    add r4, r4, #0x0c
    ldr r7, [r4, #0x18]
    ldr r6, [r5, #8]
    movw r0, #734
    cmp r6, r0
    blo .Lread_materials
    cmp r6, r7
    bge .Lread_materials
    ldr r8, [r4, #0x1c]
    ldr r4, [r4, #0x20]
    cmp r8, #0
    cmpne r4, #0
    beq .Lread_materials
.Lappend:
    ldrb r0, [r4, r6]
    cmp r0, #0
    ldrne r1, [r8, r6, lsl #2]
    cmpne r1, #0
    beq .Lread_materials
    mov r0, r5
    mov r2, r6
    bl fast_list_insert
    add r6, r6, #1
    cmp r6, r7
    blt .Lappend
.Lread_materials:
    pop {r0, r1, r4-r8, lr}
    b read_materials
.p2align 2
.Lapp_slot: .word app_got - (.Lapp_pc + 8)
.Lnames_slot: .word names_got - (.Lnames_pc + 8)

/* This call site is specific to the Objects bank. Snapshot its loaded size
 * before any material-defined sprites can extend it. */
.global load_object_bank
load_object_bank:
    push {r0, lr}
    bl load_sprite_bank
#ifdef NATIVE_SPRITE_REPLACEMENTS
    ldr r0, [sp]
    ldr r1, .Lreplacement_app_slot
.Lreplacement_app_pc:
    ldr r1, [pc, r1]
    ldr r1, [r1]
    ldr r2, .Lreplacement_fs_slot
.Lreplacement_fs_pc:
    ldr r2, [pc, r2]
    ldr r2, [r2]
    bl apply_mod_sprite_replacements
#endif
    pop {r1, lr}
    ldr r2, [r1, #0x18]
    ldr r3, .Lload_baseline
.Lload_pc:
    add r3, pc, r3
    stm r3, {r1, r2}
    bx lr

/* Keep bank entries loaded from the archive when MaterialLibrary resets.
 * The stock call still clears sprites added later by inline definitions. */
.global reset_object_bank
reset_object_bank:
    ldr r3, .Lreset_baseline
.Lreset_pc:
    add r3, pc, r3
    ldm r3, {r2, r3}
    cmp r0, r2
    bne truncate_sprite_bank
    cmp r3, r1
    movhi r1, r3
    b truncate_sprite_bank
.Lload_baseline: .word bank_baseline - (.Lload_pc + 8)
.Lreset_baseline: .word bank_baseline - (.Lreset_pc + 8)
#ifdef NATIVE_SPRITE_REPLACEMENTS
.global compare_atlas_root
compare_atlas_root:
    orr r2, r2, #0x20           @ the stored delimiter is lowercase /data/
    cmp r2, r1
    b atlas_root_continue

.global compare_materials_root
compare_materials_root:
    orr r6, r6, #0x20
    cmp r6, r7
    b materials_root_continue

.Lreplacement_app_slot: .word app_got - (.Lreplacement_app_pc + 8)
.Lreplacement_fs_slot: .word filesystem_got - (.Lreplacement_fs_pc + 8)

.global game_world_renderer
game_world_renderer:
    ldr r0, .Lmaterial_renderer_app
.Lmaterial_renderer_pc:
    ldr r0, [pc, r0]
    ldr r0, [r0]
    add r0, r0, #0x310
    bx lr
.Lmaterial_renderer_app: .word app_got - (.Lmaterial_renderer_pc + 8)

.global game_world
game_world:
    ldr r0, .Lscript_world_app
.Lscript_world_pc:
    ldr r0, [pc, r0]
    ldr r0, [r0]
    ldr r0, [r0, #0xe0]
    bx lr
.Lscript_world_app: .word app_got - (.Lscript_world_pc + 8)

.global make_object_preview_hook
make_object_preview_hook:
    ldr r12, [sp, #0x14]        @ MaterialsButton's build mode
    push {r4, lr}
    ldr r4, [sp, #8]            @ colour
    ldr lr, [sp, #12]           @ UVs
    push {r4, lr}
    push {r10, r12}             @ material ID, build mode
    bl make_object_preview
    add sp, sp, #16
    pop {r4, pc}

.global draw_preview_hook
draw_preview_hook:
    push {r4-r8, lr}
    add r4, sp, #24
    ldm r4, {r4-r7}             @ depth, texture, colour, anchor
    ldr r8, [sp, #12]           @ StandardUIDrawable + 4
    add r8, r8, #16             @ computed frame UVs
    push {r4-r8, lr}
    bl draw_preview
    add sp, sp, #24
    pop {r4-r8, pc}

.global object_preview_state
object_preview_state:
    adr r2, .Lpreview_bank_offset
    ldr r3, [r2]
    add r2, r2, r3
    ldm r2, {r2, r3}
    str r3, [r0]
    adr r3, .Lpreview_texture_offset
    ldr r12, [r3]
    add r3, r3, r12
    str r3, [r1]
    mov r0, r2
    bx lr
.Lpreview_bank_offset: .word bank_baseline - .Lpreview_bank_offset
.Lpreview_texture_offset: .word preview_texture - .Lpreview_texture_offset

.global callout_icon_slot
callout_icon_slot:
    adr r0, .Lcallout_icons_offset
    ldr r1, [r0]
    add r0, r0, r1
    bx lr
.Lcallout_icons_offset: .word callout_icons - .Lcallout_icons_offset

.global production_overlay_slot
.global default_staff_slot
default_staff_slot:
    adr r0, .Ldefault_staff_offset
    ldr r1, [r0]
    add r0, r0, r1
    bx lr
.Ldefault_staff_offset: .word default_staff_state - .Ldefault_staff_offset

.global construct_default_staff_hook
construct_default_staff_hook:
    mov r0, r4
    b construct_default_staff

.global set_default_staff_hangout_hook
set_default_staff_hangout_hook:
    push {r0-r3, r12, lr}
    mov r0, r4
    mov r1, r5
    bl default_staff_hangout_room
    str r0, [r4, #0x1d8]
    pop {r0-r3, r12, pc}

.global update_default_staff_hangout_hook
update_default_staff_hangout_hook:
    push {r0-r3, r12, lr}
    mov r0, r4
    mov r1, r6
    bl default_staff_hangout_room
    str r0, [r4, #0x1d8]
    pop {r0-r3, r12, pc}

production_overlay_slot:
    adr r0, .Lproduction_overlay_offset
    ldr r1, [r0]
    add r0, r0, r1
    bx lr
.Lproduction_overlay_offset: .word production_overlay - .Lproduction_overlay_offset

.global language_overlay_slot
language_overlay_slot:
    adr r0, .Llanguage_overlay_offset
    ldr r1, [r0]
    add r0, r0, r1
    bx lr
.Llanguage_overlay_offset: .word language_overlay - .Llanguage_overlay_offset

.global event_overlay_slot
event_overlay_slot:
    adr r0, .Levent_overlay_offset
    ldr r1, [r0]
    add r0, r0, r1
    bx lr
.Levent_overlay_offset: .word event_overlay - .Levent_overlay_offset

.global merge_event_hook
merge_event_hook:
    mov r2, r6                 @ Current Event directory.
    b merge_event

.global merge_prefab_hook
merge_prefab_hook:
    mov r3, r8                 @ Current Prefab directory.
    b merge_prefab

/* The base loader keeps existing keys. A mod layer lets the same map
 * assignment replace the value without changing the key. */
.global check_duplicate_language_key
check_duplicate_language_key:
    adr r0, .Llanguage_overlay_offset
    ldr r1, [r0]
    ldrb r0, [r0, r1]
    cmp r0, #0
    bne read_language_value
    b skip_language_value

.global active_mod_system
active_mod_system:
    ldr r0, .Lmod_system_offset
.Lmod_system_pc:
    ldr r0, [pc, r0]
    ldr r0, [r0]              @ ModSystem is the first App member.
    bx lr
.Lmod_system_offset: .word app_got - (.Lmod_system_pc + 8)

.global load_mod_fonts_hook
load_mod_fonts_hook:
    add r2, r1, #12             @ The caller stores the BMP path after the FNT path.
    b load_mod_fonts

.global finish_language_reset
finish_language_reset:
    push {r4, lr}
    add r4, sp, #48           @ ResetLanguage's locale at its original sp + 40.
    bl load_language_structure
    ldr r0, .Llanguage_table_offset
.Llanguage_table_pc:
    ldr r0, [pc, r0]
    ldr r0, [r0]
    mov r1, r4
    pop {r4, lr}
    b apply_mod_languages
.Llanguage_table_offset: .word language_table_got - (.Llanguage_table_pc + 8)

.global merge_sound_event_hook
merge_sound_event_hook:
    ldr r1, [sp, #0x24]       @ SoundBlueprintManager starts with the blueprint hash table.
    ldr r1, [r1, #4]          @ Hash table values, indexed by r7.
    ldr r1, [r1, r7, lsl #2]
    ldr r2, [sp, #8]          @ Sound definition paths and current index.
    ldr r2, [r2]
    ldr r3, [sp, #0x1c]
    add r3, r3, r3, lsl #1
    add r2, r2, r3, lsl #2
    b merge_sound_event

.macro read_inline_icon_hook hook, reader
.global \hook
\hook:
    ldr r12, [sp, #0x1a4]      @ current materials file
    ldr r2, [sp, #0x1ac]       @ Callout directory
    ldr r3, .Licon_app_slot\@
.Licon_app_pc\@:
    ldr r3, [pc, r3]
    ldr r3, [r3]
    add r3, r3, #784           @ WorldRenderer
    push {r4, lr}
    push {r12, lr}
    bl \reader
    add sp, sp, #8
    pop {r4, pc}
.Licon_app_slot\@: .word app_got - (.Licon_app_pc\@ + 8)
.endm
read_inline_icon_hook read_callout_icon_hook, read_callout_icon
read_inline_icon_hook read_toolbar_icon_hook, read_toolbar_icon

.global squad_icon_name_hook
squad_icon_name_hook:
    str r1, [sp, #0x34]        @ callout ID for the later drawable constructor
    cmp r1, #6                 @ v49 stock callout count
    bhs .Lcustom_squad_icon
    add r0, r1, r1, lsl #1
    adr r1, .Lstock_squad_icons
    ldr r2, [r1]
    add r1, r1, r2
    ldrb r2, [r1, r0, lsl #2]!
    b squad_icon_continue
.Lcustom_squad_icon:
    push {r4, lr}
    add r0, sp, #0x30          @ temporary texture-atlas sprite name
    adr r2, .Linterface_names_offset
    ldr r3, [r2]
    ldr r2, [r2, r3]
    bl find_squad_icon_name
    pop {r4, lr}
    b squad_icon_ready
.Lstock_squad_icons: .word stock_squad_icons - .Lstock_squad_icons
.Linterface_names_offset: .word interface_names_got - .Linterface_names_offset

.global make_squad_preview_hook
make_squad_preview_hook:
    ldr r12, [sp, #0x34]
    push {r4, lr}
    ldr r4, [sp, #8]           @ colour
    ldr lr, [sp, #12]          @ UVs
    push {r4, lr}
    mov r4, #13                @ emergency mode
    sub sp, sp, #8
    str r12, [sp]
    str r4, [sp, #4]
    bl make_object_preview
    add sp, sp, #16
    pop {r4, pc}
#endif

/* WorldRenderer passes width / 32 for both axes. The image carries its
 * real height at +0x1c. Keep the stock width and set the vertical grid. */
.global load_composite_image
load_composite_image:
    ldr r3, [r1, #0x1c]
    lsr r3, r3, #5
    b load_sprite_image

/* WorldObject::SetupScriptSystem passes the candidate path in r0. Use the
 * game's archive-aware check, which also falls back to the disk filesystem. */
.global object_script_exists
object_script_exists:
    mov r1, r0
    ldr r0, .Lfilesystem_slot
.Lfilesystem_pc:
    ldr r0, [pc, r0]
    ldr r0, [r0]
    b archive_file_exists
.Lfilesystem_slot: .word filesystem_got - (.Lfilesystem_pc + 8)

#ifdef NATIVE_SPRITE_REPLACEMENTS
.global game_filesystem
game_filesystem:
    ldr r0, .Lgame_filesystem_offset
.Lgame_filesystem_pc:
    ldr r0, [pc, r0]
    ldr r0, [r0]
    bx lr
.Lgame_filesystem_offset: .word filesystem_got - (.Lgame_filesystem_pc + 8)

.global decode_mod_atlas_hook
decode_mod_atlas_hook:
    mov r3, r7                  @ Image constructor's archive path
    b decode_mod_atlas

.global menu_title_image_slot
menu_title_image_slot:
    adr r0, .Lmenu_title_image
    ldr r1, [r0]
    add r0, r0, r1
    bx lr
.Lmenu_title_image: .word menu_title_image - .Lmenu_title_image

.global upload_texture_region
upload_texture_region:
    ldr r12, .Ltex_sub_image
.Ltex_sub_image_pc:
    ldr r12, [pc, r12]
    bx r12
.Ltex_sub_image: .word texture_region_got - (.Ltex_sub_image_pc + 8)
#endif

#ifdef NATIVE_MOD_SCAN
/* App's ModSystem is its first member. At this constructor call site r4 is
 * App and r0 is its WorldRenderer. Preferences and the OBB are already open. */
.global scan_mods_before_renderer
scan_mods_before_renderer:
    push {r0, lr}
    mov r0, r4
    bl read_mod_types
    mov r0, r4
    bl initialise_mods
#ifdef NATIVE_SPRITE_REPLACEMENTS
    bl refresh_menu_title
#endif
    pop {r0, lr}
    b initialise_renderer
#endif

#ifdef NATIVE_MOD_ATLAS
.p2align 2
/* The mobile composite is packed RGBA4444, with rows stored bottom first.
 * Give the native PNG packer only the band after the existing image. */
.global load_native_atlas
load_native_atlas:
    push {r4-r6, lr}
    sub sp, sp, #8
    mov r4, r7
    @ The stock packer clears offsets only after a successful pack.
    @ Clear at the start of every rebuild, including empty or failed packs.
    add r6, r9, #0x28c
    sub r0, r6, #4
    ldr r1, [r6]
    cmp r1, #0
    blne erase_sprite_offset_tree
    mov r0, #0
    str r6, [r6, #-4]
    str r0, [r6]
    str r0, [r6, #4]
    ldr r0, [r4]
    movw r1, #0x8033
    cmp r0, r1
    bne .Latlas_ready
#ifdef NATIVE_SPRITE_REPLACEMENTS
    mov r0, r4
    mov r1, r5                    @ FileSystem from SetupSpriteBanks
    bl apply_mod_composite_sheets
#endif
    mov r0, #0
    str r0, [sp]
    movw r0, #0x0d33             @ GL_MAX_TEXTURE_SIZE
    mov r1, sp
    bl gl_get_integer
    ldr r2, [sp]
    mov r0, #8192
    cmp r2, r0
    movhi r2, r0
    ldr r0, [r4, #4]
    ldr r1, [r4, #8]
    cmp r0, r2
    bhi .Latlas_ready
    cmp r1, r2
    bhs .Latlas_ready
    tst r0, #31
    tsteq r1, #31
    bne .Latlas_ready
    adr r5, .Latlas_state_offset
    ldr r6, [r5]
    add r5, r5, r6
    str r4, [r5]
    str r2, [r5, #4]
    mov r0, r9
    bl load_user_sprite_images
    mov r1, #0
    str r1, [r5]
    cmp r0, #0
    beq .Latlas_ready
    mov r4, r0
    mov r0, r7
    bl bitmap_destroy
    mov r0, r7
    bl delete_object
.Latlas_ready:
    mov r7, r4
    ldr r8, [r7, #4]               @ displaced stock instruction
    add sp, sp, #8
    pop {r4-r6, pc}
.Latlas_state_offset: .word native_atlas_state - .Latlas_state_offset

/* Stock cleanup and return already use this local for the result bitmap. */
.global defer_atlas_allocation
defer_atlas_allocation:
    mov r0, #0
    str r0, [sp, #0x3c]
    b list_sprite_paths

.global check_decoded_sprite
check_decoded_sprite:
    ldrb r0, [r10, #0xd]
    cmp r0, #0
    beq .Ldiscard_sprite
    ldr r0, [r10, #4]
    ldr r1, [r10, #8]
    cmp r0, #1
    cmphs r1, #1
    bhs .Ladd_sprite
.Ldiscard_sprite:
    mov r0, r10
    bl bitmap_destroy
    mov r0, r10
    bl delete_object
    b close_sprite_reader
.Ladd_sprite:
    str r10, [sp, #0xa0]           @ displaced stock instruction
    b add_valid_sprite

/* NamedRectangle is a 12-byte libc++ string followed by x, y, w, h. The
 * free band is expressed in the same top-origin coordinates as materials. */
.global reserve_native_atlas_space
reserve_native_atlas_space:
    sub sp, sp, #32
    adr r0, .Latlas_state_offset
    ldr r1, [r0]
    add r0, r0, r1
    ldm r0, {r1, r10}
    bic r10, r10, #31
    ldr r3, [r1, #8]
    ldr r1, [r1, #4]
    sub r12, r10, r3
    mov r0, #0
    str r0, [sp]
    str r0, [sp, #4]
    str r0, [sp, #8]
    str r0, [sp, #12]
    str r3, [sp, #16]
    str r1, [sp, #20]
    str r12, [sp, #24]
    str lr, [sp, #28]
    mov r0, r2
    mov r1, sp
    bl append_rectangle
    ldr lr, [sp, #28]
    add sp, sp, #32
    bx lr

.global native_atlas_pack_failed
native_atlas_pack_failed:
    adr r0, .Latlas_full
    bl debug_log
    b free_sprite_inputs
.Latlas_full: .asciz "Active mod sprites do not fit in the mobile composite texture"
.p2align 2

/* Use only the rows required by the packed sheets. Copy the base image
 * at the top, so every existing sprite still has the same x/y coordinates. */
.global allocate_packed_atlas
allocate_packed_atlas:
    ldr r0, [sp, #0x60]
    ldr r1, [sp, #0x68]
    adr r2, .Latlas_state_offset
    ldr r3, [r2]
    ldr r4, [r2, r3]
    ldr r10, [r4, #8]
    cmp r1, #0
    beq free_sprite_inputs
.Latlas_max_y:
    ldr r2, [r0, #16]
    ldr r3, [r0, #24]
    add r2, r2, r3
    cmp r2, r10
    movhi r10, r2
    add r0, r0, #28
    subs r1, r1, #1
    bne .Latlas_max_y
    mov r0, #24
    bl new_object
    mov r5, r0
    movw r0, #0x8033
    ldr r1, [r4, #4]
    mov r2, #0
    stm r5, {r0, r1, r10}
    str r2, [r5, #0xc]
    str r2, [r5, #0x14]
    mul r0, r1, r10
    lsl r0, r0, #1
    bl new_array
    str r0, [r5, #0x10]
    ldr r1, [r5, #4]
    ldr r2, [r4, #8]
    sub r2, r10, r2
    mul r1, r2, r1
    lsl r1, r1, #1
    bl zero_bytes
    ldr r0, [r5, #0x10]
    ldr r1, [r5, #4]
    ldr r2, [r4, #8]
    sub r3, r10, r2
    mul r3, r3, r1
    mul r2, r2, r1
    add r0, r0, r3, lsl #1
    lsl r2, r2, #1
    ldr r1, [r4, #0x10]
    bl copy_bytes
    str r5, [sp, #0x3c]
    ldr r0, [sp, #0x34]           @ displaced stock instruction
    b clear_old_sprite_offsets

/* Stock Blit expects 32-bit rows. Keep the game's RGBA4444 upload format and
 * convert only the new PNG, including the original mod transparency key. */
.global copy_sprite_rgba4444
copy_sprite_rgba4444:
    push {r4, lr}
    ldr r1, [sp, #12]            @ source Bitmap* (stock stack argument)
    ldr r12, [sp, #16]           @ destination x
    ldr r3, [sp, #20]            @ destination y, bottom origin
    ldr r2, [r0, #4]             @ destination stride in pixels
    mla r3, r3, r2, r12
    ldr r0, [r0, #0x10]
    add r0, r0, r3, lsl #1
    bl copy_mod_sprite_pixels
    pop {r4, pc}

/* BiographyGenerator samples the CPU atlas directly. Stock .csimage has
 * a legacy row table; the merged bitmap holds linear RGBA4444 pixels. */
.global read_portrait_pixel
read_portrait_pixel:
    ldr r0, [r5, #0x14]
    cmp r0, #0
    bxne lr
    mov r0, r5
    mov r2, r6
    bl .Lread_packed_pixel
    mov r3, r0
    b store_portrait_pixel

.global read_image_pixel
read_image_pixel:
    ldr r0, [r4, #0x14]
    cmp r0, #0
    bxne lr
    mov r0, r4
    mov r12, lr
    bl .Lread_packed_pixel
    mov lr, r12
    mov r1, r0
    b store_image_pixel

.Lread_packed_pixel:
    ldr r3, [r0, #4]
    ldr r0, [r0, #0x10]
    mla r1, r2, r3, r1
    add r0, r0, r1, lsl #1
    ldrh r3, [r0]
    ubfx r0, r3, #12, #4
    ubfx r1, r3, #8, #4
    ubfx r2, r3, #4, #4
    and r3, r3, #15
    orr r0, r0, r1, lsl #8
    orr r0, r0, r2, lsl #16
    orr r0, r0, r3, lsl #24
    orr r0, r0, r0, lsl #4
    bx lr

/* Material definitions can rebuild the callout mappings when a save opens. */
.global base_materials_first
base_materials_first:
#ifdef NATIVE_SPRITE_REPLACEMENTS
    push {r4-r6, lr}
    sub sp, sp, #16
    stm sp, {r0-r3}
    bl clear_callout_icons
    ldm sp, {r0-r3}
    add sp, sp, #16
    pop {r4-r6, lr}
#endif

/* GetFilePaths appends the base after the mods. For tables with overrides,
 * apply the base first and preserve the relative order of the mods. */
.global base_file_first
base_file_first:
    push {r4-r6, lr}
    sub sp, sp, #16
    mov r4, r2
    bl get_mod_file_paths
    ldr r0, [r4, #8]
    subs r0, r0, #1
    ble .Lmaterials_done
    add r0, r0, r0, lsl #1
    lsl r2, r0, #2
    ldr r4, [r4]
    add r0, r4, r2
    ldm r0, {r0, r1, r3}
    stm sp, {r0, r1, r3}
    add r0, r4, #12
    mov r1, r4
    bl move_bytes
    ldm sp, {r0, r1, r2}
    stm r4, {r0, r1, r2}
.Lmaterials_done:
    add sp, sp, #16
    pop {r4-r6, pc}

/* The stock first-definition rule remains useful for the base file. Local
 * files apply overrides in the user-selected order after it. */
.macro allow_override name, apply, skip
.global \name
\name:
    ldr r12, [sp, #0x170]        @ current material file index in ReadMaterials
    cmp r12, #0
    bne \apply
    b \skip
.endm
allow_override check_duplicate_object, apply_object_definition, skip_object_definition
allow_override check_duplicate_equipment, apply_equipment_definition, skip_equipment_definition
allow_override check_duplicate_material, apply_material_definition, skip_material_definition
allow_override check_duplicate_room, apply_room_definition, skip_room_definition
allow_override check_duplicate_callout, apply_callout_definition, skip_callout_definition

/* The tablet language loader only names archive files. Load matching local
 * files after each base layer, in the same order as the active mods. */
.global load_mod_language
load_mod_language:
#ifdef NATIVE_SPRITE_REPLACEMENTS
    b load_language_table
#else
    push {r4-r8, lr}
    sub sp, sp, #16
    mov r4, r0
    mov r5, r1
    bl load_language_table
    ldr r0, .Llanguage_app_slot
.Llanguage_app_pc:
    ldr r0, [pc, r0]
    ldr r0, [r0]
    mov r1, #0
    str r1, [sp]
    str r1, [sp, #4]
    str r1, [sp, #8]
    mov r1, r5
    mov r2, sp
    mov r3, #0
    bl get_mod_file_paths
    ldr r5, [sp]
    cmp r5, #0
    beq .Llanguage_done
    ldr r7, [sp, #8]
    mov r6, r5
    cmp r7, #0
    ble .Llanguage_free_list
.Llanguage_next:
    mov r0, r4
    mov r1, r6
    mov r2, #0
    bl load_language_table
    ldrb r0, [r6]
    tst r0, #1
    ldrne r0, [r6, #8]
    blne delete_object
    add r6, r6, #12
    subs r7, r7, #1
    bne .Llanguage_next
.Llanguage_free_list:
    sub r0, r5, #8
    bl delete_array
.Llanguage_done:
    add sp, sp, #16
    pop {r4-r8, pc}
.Llanguage_app_slot: .word app_got - (.Llanguage_app_pc + 8)
#endif

/* A grant supplied by Lua may have no entry in the tablet's fixed icon map.
 * Reset to the generic icon on a miss, including when a row is reused. */
.global set_grant_icon
set_grant_icon:
    cmp r0, #0
    addne r1, r0, #0x14
    adreq r1, .Ldefault_grant_icon
    sub r0, r11, #0xbc
    b set_drawable_id
.Ldefault_grant_icon:
    .byte 20                     @ libc++ short string, 10 bytes
    .asciz "IconGrants"
.p2align 2
#endif

#ifdef TRACE_NATIVE_CRASHES
/* Android's crash_dump helper is unavailable in the test device's ARM bridge.
 * Log the ARM register frame before terminating the diagnostic process. */
.global install_crash_trace
install_crash_trace:
    push {r0, lr}
    sub sp, sp, #16
    adr r0, .Ltrace_fault
    mov r1, #0
    movw r2, #4                    @ SA_SIGINFO
    movt r2, #0x8000               @ SA_RESETHAND
    mov r3, #0
    stm sp, {r0-r3}
    mov r0, #11                   @ SIGSEGV
    mov r1, sp
    mov r2, #0
    bl set_signal_action
    add sp, sp, #16
    pop {r0, lr}
    b app_constructor

.Ltrace_fault:
    push {r4, lr}
    sub sp, sp, #24
    adr r4, .Ltrace_fault
    ldr r3, .Ltrace_offset
    sub r4, r4, r3
    ldr r3, [r2, #92]             @ ucontext.uc_mcontext.arm_pc
    sub r3, r3, r4
    ldr r0, [r2, #88]             @ ucontext.uc_mcontext.arm_lr
    sub r0, r0, r4
    str r0, [sp]
    ldr r0, [r2, #100]
    str r0, [sp, #4]
    ldr r0, [r2, #32]
    str r0, [sp, #8]
    ldr r0, [r2, #36]
    str r0, [sp, #12]
    ldr r0, [r2, #48]
    str r0, [sp, #16]
    mov r0, #6
    adr r1, .Ltrace_tag
    adr r2, .Ltrace_format
    bl android_log_print
    mov r0, #139
    b exit_process
.Ltrace_offset: .word .Ltrace_fault
.Ltrace_tag: .asciz "PAToolsNative"
.Ltrace_format: .asciz "ARM fault pc=%08x lr=%08x address=%08x r0=%08x r1=%08x r4=%08x"
.p2align 2
#endif
