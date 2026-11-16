/* Native layouts for the v49 ARM engine. The build pins the original ELF. */
#include <dirent.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>

typedef union {
    uint8_t short_size;
    struct { unsigned capacity, size; const char *data; } long_string;
} GameString;

typedef struct {
    int format, width, height;
    uint8_t reserved[4];
    uint16_t *packed;
    const uint32_t *const *rows;
} Bitmap;

typedef struct {
    Bitmap *bitmap;
    int texture;
    uint8_t owns_bitmap, mipmaps, reserved[2];
    GameString path;
    int width, height;
    uint8_t padding[9], linear_filter;
} Image;
typedef struct { GameString name; int x, y, w, h, rotation; uint8_t flags; } Sprite;
typedef struct {
    Image *image;
    uint8_t reserved[20];
    int count;
    const Sprite *const *sprites;
    const uint8_t *present;
} SpriteBank;
typedef struct { GameString path; uint8_t reserved[96]; } Mod;
typedef struct { const Mod *mods; int capacity, count; } ModList;
typedef struct { const GameString *items; int capacity, count; } GameStringList;
typedef struct { int x, y, w, h; } Rect;
typedef struct { void (*const *vtable)(void *); } BinaryReader;
typedef struct TextReader TextReader;
typedef struct UiTexture UiTexture;
typedef struct Directory Directory;
typedef struct LanguageTable LanguageTable;
typedef struct { UiTexture *texture; void *owner; } TextureRef;
typedef struct { float x, y, w, h; } UVs;
typedef struct {
    GameString name;
    uint8_t reserved[88];
    int sprite;
    uint8_t properties[8];
    int toolbar_sprite;
} ObjectTemplate;
typedef struct {
    GameString name;
    int price, max_count, vehicle, entity, entity_count, interface_sprite;
} CalloutTemplate;
typedef struct {
    int kind, material, container, room, stack_room, distribution, first_slot, last_slot, condition, processor;
} ProductionRule;
typedef struct {
    int processor, input;
    uint32_t settings[5];
    int *resources;
    int resources_capacity, resources_count;
    uint32_t qualifiers[4];
} ProcessorRule;
typedef struct { ProductionRule *items; int capacity, count; } ProductionRules;
typedef struct { ProcessorRule *items; int capacity, count; } ProcessorRules;
typedef struct { uint32_t reserved; ProductionRules rules; } ProductionSystem;
typedef struct {
    uint8_t lists[24];
    GameString name;
    uint8_t fields[44];
} WorldEventTemplate;
typedef struct {
    int grow_by, capacity;
    WorldEventTemplate *items;
    const uint8_t *present;
    int count;
    const int *free_indices;
    int first_free;
} EventTemplates;
typedef struct EventSystem EventSystem;
typedef struct {
    GameString name;
    uint8_t settings[16];
    int *objects;
    int object_capacity, object_count;
} JobTemplate;
typedef struct { JobTemplate *items; int capacity, count; } JobTemplates;
typedef struct {
    GameString name, icon;
    int width, height, room;
    int *objects;
    int capacity, count, orientation, base_id;
} Prefab;
typedef struct { Prefab *items; int capacity, count; } Prefabs;
typedef struct {
    GameString name;
    int type;
    uint8_t reserved[12];
    GameString text;
} DirectoryData;

/* Directory's DArray<DirectoryData *> preserves repeated Properties fields. */
struct Directory {
    uint8_t reserved[40];
    int grow_by, capacity;
    const DirectoryData *const *items;
    const uint8_t *present;
};

typedef struct DefaultStaff {
    struct DefaultStaff *next;
    int type;
    bool needs_rest;
    char hangout_room[];
} DefaultStaff;
typedef struct { GameString name; } SoundInstanceBlueprint;
typedef struct SoundInstanceNode {
    SoundInstanceBlueprint *instance;
    struct SoundInstanceNode *next, *previous;
} SoundInstanceNode;
typedef struct { SoundInstanceNode *first, *last; int count; unsigned revision; } SoundEventBlueprint;
typedef struct SampleGroup SampleGroup;
typedef struct CalloutIcon {
    UVs tiles;
    struct CalloutIcon *next;
    bool toolbar;
    char name[];
} CalloutIcon;

enum { MODE_OBJECTS = 5, MODE_STAFF = 8, MODE_EMERGENCIES = 13, FIRST_SPECIAL_ACTION = 9999 };

extern SpriteBank *object_preview_state(int *stock_count, UiTexture ***texture_slot);
extern CalloutIcon **callout_icon_slot(void);
extern DefaultStaff **default_staff_slot(void);
extern int lookup_object_id(const GameString *);
extern int lookup_zone_id(const GameString *);
extern void entity_ctor(void *);
extern void worker_ctor(void *);
extern bool gets_tired(int);
extern bool *production_overlay_slot(void);
extern bool *language_overlay_slot(void);
extern bool *event_overlay_slot(void);
extern void load_production_rules(void *, const GameString *);
extern int append_production_rule(ProductionRules *, const ProductionRule *, int);
extern int append_processor_rule(ProcessorRules *, const ProcessorRule *, int);
extern void create_ui_texture(UiTexture **texture);
extern void build_ui_texture(UiTexture *texture, const int *dimensions);
extern void *make_atlas_drawable(void *, const TextureRef *, const void *, const GameString *,
                                 const void *, const UVs *);
extern void *make_texture_drawable(void *, const TextureRef *, const void *, const UVs *);
extern const ObjectTemplate *get_object_template(int);
extern const CalloutTemplate *get_callout_template(int);
extern GameString *copy_game_string(GameString *, const GameString *);
extern const Directory *directory_child(const Directory *, const GameString *);
extern const DirectoryData *directory_data(const Directory *, const GameString *);
extern double directory_number(const Directory *, const GameString *);
extern void read_sprite_definition(Sprite *, Directory *);
extern void get_mod_sprite_offset(int *, void *, const GameString *);
extern int add_user_defined_sprite(void *, const GameString *, Directory *, const GameString *);
extern void *game_world_renderer(void);
extern bool language_has_phrase(const LanguageTable *, const GameString *);
extern const void *language_lookup(const LanguageTable *, const GameString *);
extern void draw_texture_box(void *, const void *, const void *, const void *, float,
                             const TextureRef *, const void *, int);
extern void draw_sprite_bank_box(void *, const void *, const void *, const void *, float,
                                 const SpriteBank *, const UVs *, const void *, int);

extern const Sprite *lookup_sprite(SpriteBank *, const GameString *);
extern void sprite_rect(const Sprite *, const float *, int *, int *, int *, int *, int *, int *, int *);
extern BinaryReader *get_binary_reader(void *, const GameString *, bool);
extern TextReader *get_text_reader(void *, const GameString *, bool);
extern void list_archive(void *, const GameString *, const GameString *, GameStringList *, bool, bool);
extern void list_directory(const GameString *, const GameString *, GameStringList *, bool);
extern int fast_list_insert(GameStringList *, const GameString *, int);
extern void *active_mod_system(void);
extern void get_mod_file_paths(void *, const GameString *, GameStringList *, bool);
extern void destroy_file_paths(GameStringList *);
extern bool load_bitmap_font(void *, const GameString *, int, float);
extern void load_language_table(LanguageTable *, const GameString *, bool);
extern void load_events(EventSystem *, const GameString *);
extern int append_event(EventTemplates *, const WorldEventTemplate *);
extern void destroy_event(WorldEventTemplate *);
extern void initialise_event(WorldEventTemplate *);
extern int append_job(JobTemplates *, const JobTemplate *, int);
extern int append_prefab(Prefabs *, const Prefab *, int);
extern void initialise_prefab(Prefab *);
extern SampleGroup *find_sample_group(void *, const char *);
extern SampleGroup *create_sample_group(void *, const char *);
extern void destroy_sample_group(SampleGroup *);
extern void remove_sound_instance(SoundEventBlueprint *, int);
extern void destroy_sound_instance(SoundInstanceBlueprint *);
extern void clear_sound_event(SoundEventBlueprint *);
extern void decode_bitmap(Bitmap *, BinaryReader *, const GameString *);
extern void construct_sprite_bank(SpriteBank *);
extern void destroy_sprite_bank(SpriteBank *);
extern void load_sprite_bank_path(SpriteBank *, const GameString *);
extern void *game_filesystem(void);
extern Image **menu_title_image_slot(void);
extern bool make_image_texture(Image *, bool, bool, bool, bool);
extern void gl_get_integer(unsigned, int *);
extern void gl_bind_texture(unsigned, unsigned);
extern void gl_generate_mipmap(unsigned);
extern void upload_texture_region(unsigned, int, int, int, int, int, unsigned, unsigned, const void *);
extern void bitmap_destroy(Bitmap *);
extern int upload_bitmap(Bitmap *, bool, int, bool);
extern void debug_log(const char *, ...);
extern void copy_bytes(void *, const void *, unsigned);
extern void *new_array(unsigned);
extern void *new_object(unsigned);
extern void delete_array(void *);
extern void zero_bytes(void *, unsigned);
extern void get_app_save_folder(GameString *);
extern void append_game_string(GameString *, const char *, unsigned);
extern void assign_game_string(GameString *, const char *, unsigned);
extern void concat_game_string(GameString *, const GameString *, const GameString *);
extern bool disk_file_exists(const GameString *);
extern void split_game_string(const GameString *, char, void *);
extern void delete_object(void *);

static bool read_material_sheet(const GameString *materials, uint32_t dimensions[2]);
static void read_frames(const Sprite *sprite, Rect *frames);
static bool frame_fits(const Rect *frame, int columns, int rows);

typedef struct { GameString device, game; } LocalePair;
typedef struct { LocalePair *begin, *end, *capacity; } LocaleVector;
typedef struct { GameString *begin, *end, *capacity; } LabelVector;

extern void set_supported_locales(void *);
extern void append_locale_pair(LocaleVector *, LocalePair *);
extern void append_language_label(LabelVector *, const GameString *);
extern int register_static_destructor(void (*)(void *), void *, void *);

static const char *string_data(const GameString *text) {
    return text->short_size & 1 ? text->long_string.data : (const char *)text + 1;
}

static GameString borrow_string(const char *text, unsigned length) {
    return (GameString){.long_string = {((length + 2) & ~1u) | 1u, length, text}};
}

static bool load_layer_font(void *font_set, ModList *layer, const GameString *path) {
    GameStringList files = {0};
    get_mod_file_paths(layer, path, &files, false);
    bool loaded = files.count > 0 && load_bitmap_font(font_set, &files.items[0], 0, 0.0f);
    destroy_file_paths(&files);
    return loaded;
}

bool load_mod_fonts(void *font_set, const GameString *fnt, const GameString *bmp) {
    const ModList *mods = active_mod_system();
    if (!mods) return false;
    for (int i = mods->count; i > 0; --i) {
        ModList layer = {&mods->mods[i - 1], 1, 1};
        if (load_layer_font(font_set, &layer, fnt) || load_layer_font(font_set, &layer, bmp)) {
            return true;
        }
    }
    return false;
}

void add_base_needs_file(void *mods, const GameString *path, GameStringList *files, bool include_base) {
    (void)mods;
    (void)include_base;
    fast_list_insert(files, path, files->count);
}

void list_needs_files(const ModList *mods, const GameString *path, GameStringList *files, bool include_base) {
    // The female base file is optional. Its stock definitions take precedence
    // over the common defaults, and both precede any mod providers.
    static const char female_path[] = "data/needs-female.txt";
    GameString female = borrow_string(female_path, sizeof(female_path) - 1);
    bool female_prison = files->count != 0;
    if (include_base) fast_list_insert(files, path, files->count);
    for (int i = 0; i < mods->count; ++i) {
        ModList layer = {&mods->mods[i], 1, 1};
        get_mod_file_paths(&layer, path, files, false);
        if (female_prison) get_mod_file_paths(&layer, &female, files, false);
    }
}

void set_supported_locales_with_chinese(void *app) {
    static const char device[] = "zh";
    static const char game[] = "simplifiedchinese";
    set_supported_locales(app);
    LocaleVector *locales = (void *)((char *)app + 0x820);
    LocalePair entry = {0};
    assign_game_string(&entry.device, device, sizeof(device) - 1);
    assign_game_string(&entry.game, game, sizeof(game) - 1);
    append_locale_pair(locales, &entry);
    // The original final locale is a device alias for Brazilian Portuguese.
    // Keep picker indices aligned and leave the alias available to Auto.
    LocalePair *alias = locales->end - 2;
    entry = *alias;
    *alias = locales->end[-1];
    locales->end[-1] = entry;
}

int register_language_labels(void (*destroy)(void *), LabelVector *labels, void *dso) {
    static const char chinese[] = "简体中文";
    const GameString label = borrow_string(chinese, sizeof(chinese) - 1);
    append_language_label(labels, &label);
    return register_static_destructor(destroy, labels, dso);
}

void load_event_layers(EventSystem *system, const GameString *base) {
    load_events(system, base);
    void *mods = active_mod_system();
    if (!mods) return;
    GameStringList files = {0};
    get_mod_file_paths(mods, base, &files, false);
    bool *overlay = event_overlay_slot();
    *overlay = true;
    for (int i = 0; i < files.count; ++i) {
        load_events(system, &files.items[i]);
        debug_log("PATools events: %s\n", string_data(&files.items[i]));
    }
    *overlay = false;
    destroy_file_paths(&files);
}

static const char *definition_name(const Directory *entry) {
    const GameString key = borrow_string("Name", 4);
    const DirectoryData *name = directory_data(entry, &key);
    return name && name->type == 4 ? string_data(&name->text) : "";
}

int merge_event(EventTemplates *events, const WorldEventTemplate *empty, const Directory *entry) {
    if (*event_overlay_slot()) {
        const char *name = definition_name(entry);
        if (*name) {
            for (int i = 0; i < events->capacity; ++i) {
                WorldEventTemplate *existing = &events->items[i];
                if (events->present[i] && !strcmp(string_data(&existing->name), name)) {
                    destroy_event(existing);
                    initialise_event(existing);
                    return i;
                }
            }
        }
    }
    return append_event(events, empty);
}

int merge_job(JobTemplates *jobs, const JobTemplate *incoming, int end) {
    const char *name = string_data(&incoming->name);
    for (int i = 0; *name && i < jobs->count; ++i) {
        JobTemplate *existing = &jobs->items[i];
        if (!strcmp(string_data(&existing->name), name)) {
            int *objects = 0;
            if (incoming->object_count > 0) {
                size_t size = incoming->object_count * sizeof(*objects);
                objects = new_array(size);
                copy_bytes(objects, incoming->objects, size);
            }
            if (existing->objects) delete_array(existing->objects);
            copy_bytes(existing->settings, incoming->settings, sizeof(existing->settings));
            existing->objects = objects;
            existing->object_capacity = existing->object_count = incoming->object_count;
            debug_log("PATools jobs: replaced %s at %d\n", name, i);
            return i;
        }
    }
    return append_job(jobs, incoming, end);
}

int merge_prefab(Prefabs *prefabs, const Prefab *empty, int end, const Directory *entry) {
    const char *name = definition_name(entry);
    for (int i = 0; *name && i < prefabs->count; ++i) {
        Prefab *existing = &prefabs->items[i];
        if (!strcmp(string_data(&existing->name), name)) {
            if (existing->name.short_size & 1) delete_object((void *)existing->name.long_string.data);
            if (existing->icon.short_size & 1) delete_object((void *)existing->icon.long_string.data);
            if (existing->objects) delete_array(existing->objects);
            initialise_prefab(existing);
            debug_log("PATools prefabs: replaced %s at %d\n", name, i);
            return i;
        }
    }
    return append_prefab(prefabs, empty, end);
}

void list_production_files(const ModList *mods, const GameString *path, GameStringList *files, bool include_base) {
    static const char processors_path[] = "data/processors.txt";
    const GameString processors = borrow_string(processors_path, sizeof(processors_path) - 1);
    if (include_base) fast_list_insert(files, path, files->count);
    for (int i = 0; i < mods->count; ++i) {
        ModList layer = {&mods->mods[i], 1, 1};
        get_mod_file_paths(&layer, path, files, false);
        get_mod_file_paths(&layer, &processors, files, false);
    }
}

void load_production_layer(ProductionSystem *system, const GameString *file) {
    bool *overlay = production_overlay_slot();
    const char *path = string_data(file);
    *overlay = strcmp(path, "data/production.txt") != 0;
    load_production_rules(system, file);
    bool loaded_mod = *overlay;
    *overlay = false;
    if (loaded_mod) {
        debug_log("PATools production: %s (%d total production rules)\n", path, system->rules.count);
    }
}

int merge_production_rule(ProductionRules *rules, const ProductionRule *incoming, int end) {
    if (*production_overlay_slot()) {
        for (int i = 0; i < rules->count; ++i) {
            ProductionRule *existing = &rules->items[i];
            // The processor is a rule parameter. The remaining fields
            // distinguish the storage and distribution rules for one object.
            if (!memcmp(existing, incoming, offsetof(ProductionRule, processor))) {
                copy_bytes(existing, incoming, sizeof(*existing));
                return i;
            }
        }
    }
    return append_production_rule(rules, incoming, end);
}

int merge_processor_rule(ProcessorRules *rules, const ProcessorRule *incoming, int end) {
    if (*production_overlay_slot()) {
        for (int i = 0; i < rules->count; ++i) {
            ProcessorRule *existing = &rules->items[i];
            if (existing->processor != incoming->processor || existing->input != incoming->input) continue;
            int *resources = 0;
            if (incoming->resources_count > 0) {
                size_t size = incoming->resources_count * sizeof(*resources);
                resources = new_array(size);
                copy_bytes(resources, incoming->resources, size);
            }
            if (existing->resources) delete_array(existing->resources);
            copy_bytes(existing, incoming, sizeof(*existing));
            existing->resources = resources;
            existing->resources_capacity = existing->resources_count;
            return i;
        }
    }
    return append_processor_rule(rules, incoming, end);
}

void clear_callout_icons(void) {
    CalloutIcon **slot = callout_icon_slot();
    while (*slot) {
        CalloutIcon *entry = *slot;
        *slot = entry->next;
        delete_object(entry);
    }
    DefaultStaff **staff = default_staff_slot();
    while (*staff) {
        DefaultStaff *entry = *staff;
        *staff = entry->next;
        delete_object(entry);
    }
}

static const DefaultStaff *find_default_staff(int type) {
    for (const DefaultStaff *staff = *default_staff_slot(); staff; staff = staff->next) {
        if (staff->type == type) return staff;
    }
    return NULL;
}

static void read_default_staff(const GameString *name, const Directory *entry) {
    bool behaviour = false, entity = false, staff = false, scripted = false, needs = false;
    for (int i = 0; i < entry->capacity; ++i) {
        if (!entry->present[i] || !entry->items[i]) continue;
        const DirectoryData *data = entry->items[i];
        if (data->type != 4 || strcmp(string_data(&data->name), "Properties")) continue;
        const char *value = string_data(&data->text);
        if (!strcmp(value, "DefaultBehaviour")) behaviour = true;
        else if (!strcmp(value, "Entity")) entity = true;
        else if (!strcmp(value, "Staff")) staff = true;
        else if (!strcmp(value, "Scripted")) scripted = true;
        else if (!strcmp(value, "StaffNeeds")) needs = true;
    }
    DefaultStaff **slot = default_staff_slot();
    if (!behaviour && !*slot) return;
    int type = lookup_object_id(name);
    if (type < 0) return;
    while (*slot) {
        if ((*slot)->type != type) { slot = &(*slot)->next; continue; }
        DefaultStaff *previous = *slot;
        *slot = previous->next;
        delete_object(previous);
    }
    if (!behaviour || !entity || !staff || scripted) return;
    GameString key = borrow_string("HangOutRoom", 11);
    const DirectoryData *room = directory_data(entry, &key);
    const char *room_name = room && room->type == 4 ? string_data(&room->text) : "";
    size_t size = strlen(room_name) + 1;
    DefaultStaff *config = new_object(sizeof(*config) + size);
    DefaultStaff **head = default_staff_slot();
    *config = (DefaultStaff){*head, type, needs};
    copy_bytes(config->hangout_room, room_name, size);
    *head = config;
}

/* Only the factory's generic Entity fallback uses this hook. Stock subclasses
 * and script-driven entities keep their original constructors and vtables. */
void *construct_default_staff(int type) {
    bool worker = find_default_staff(type) != NULL;
    void *object = new_object(worker ? 0x1e0 : 0x1d0);
    if (worker) worker_ctor(object); else entity_ctor(object);
    return object;
}

int default_staff_hangout_room(const void *entity, int fallback) {
    int type = *(const int *)((const uint8_t *)entity + 0x18);
    const DefaultStaff *staff = find_default_staff(type);
    if (!staff || !staff->hangout_room[0]) return fallback;
    GameString room = borrow_string(staff->hangout_room, strlen(staff->hangout_room));
    return lookup_zone_id(&room);
}

bool default_staff_gets_tired(int type) {
    const DefaultStaff *staff = find_default_staff(type);
    return staff ? staff->needs_rest : gets_tired(type);
}

int register_material_sprite(void *library, const GameString *file, Directory *entry, const GameString *name) {
    const char *path = string_data(file);
    if (path[0] == '/') {
        void *renderer = game_world_renderer();
        int offset[2];
        get_mod_sprite_offset(offset, renderer, file);
        uint32_t size[2];
        if (offset[0] < 0 || offset[1] <= 0 || !read_material_sheet(file, size)) {
            // The original parser uses the same sprite for omitted definitions.
            debug_log("PATools skipped sprite without a packed atlas: %s in %s\n", string_data(name), path);
            return 457; // Nothing in the pinned v49 Objects sprite bank.
        }
        Sprite sprite;
        zero_bytes(&sprite, sizeof(sprite));
        read_sprite_definition(&sprite, entry);
        if (sprite.name.short_size & 1) delete_object((void *)sprite.name.long_string.data);
        // Keep the stock rotation arithmetic bounded before asking for each frame.
        if ((unsigned)sprite.x > 256 || (unsigned)sprite.y > 256 ||
            (unsigned)sprite.w > 256 || (unsigned)sprite.h > 256 || (unsigned)sprite.rotation > 256) {
            goto invalid_frame;
        }
        Rect frames[8];
        read_frames(&sprite, frames);
        for (unsigned i = 0; i < 8; ++i) {
            if (!frame_fits(&frames[i], size[0] / 32, size[1] / 32)) goto invalid_frame;
        }
    }
    return add_user_defined_sprite(library, file, entry, name);
invalid_frame:
    debug_log("PATools skipped sprite outside its atlas: %s in %s\n", string_data(name), path);
    return 457;
}

void find_squad_icon_name(GameString *target, int id, const GameStringList *interface_names) {
    static const char fallback[] = "Blank";
    const CalloutTemplate *callout = get_callout_template(id);
    int sprite = callout->interface_sprite;
    GameString blank = borrow_string(fallback, sizeof(fallback) - 1);
    zero_bytes(target, sizeof(*target));
    copy_game_string(target, sprite >= 0 && sprite < interface_names->count ? &interface_names->items[sprite] : &blank);
}

/* Names of callouts that came from a mod's materials file. A zero-tile entry
 * marks a callout that has no icon of its own. */
static CalloutIcon *note_mod_callout(const char *name) {
    CalloutIcon **slot = callout_icon_slot();
    for (CalloutIcon *icon = *slot; icon; icon = icon->next) {
        if (!icon->toolbar && !icon->tiles.w && !strcmp(icon->name, name)) return icon;
    }
    size_t size = strlen(name) + 1;
    CalloutIcon *marker = new_object(sizeof(*marker) + size);
    *marker = (CalloutIcon){{0, 0, 0, 0}, *slot, false};
    copy_bytes(marker->name, name, size);
    *slot = marker;
    return marker;
}

static bool is_mod_callout(const GameString *name) {
    const char *text = string_data(name);
    for (CalloutIcon *icon = *callout_icon_slot(); icon; icon = icon->next) {
        if (!icon->toolbar && !icon->tiles.w && !strcmp(icon->name, text)) return true;
    }
    return false;
}

static GameString *read_inline_icon(GameString *target, const GameString *name, const Directory *entry,
                                   void *renderer, const GameString *materials_file, bool toolbar) {
    copy_game_string(target, name);
    const char *icon_name = string_data(name);
    CalloutIcon **slot = callout_icon_slot();
    while (*slot) {
        if ((*slot)->toolbar != toolbar || strcmp((*slot)->name, icon_name)) {
            slot = &(*slot)->next;
            continue;
        }
        CalloutIcon *previous = *slot;
        *slot = previous->next;
        delete_object(previous);
    }
    // Reuse this marker for a valid icon, keeping one record per name and kind.
    CalloutIcon *icon = !toolbar && string_data(materials_file)[0] == '/' ? note_mod_callout(icon_name) : NULL;
    GameString sprite_key = toolbar ? borrow_string("ToolbarSprite", 13) : borrow_string("Sprite", 6);
    const Directory *definition = directory_child(entry, &sprite_key);
    if (!definition) return target;

    const char *file = string_data(materials_file);
    static const char materials_suffix[] = "data/materials.txt";
    size_t file_length = strlen(file);
    if (file_length <= sizeof(materials_suffix) - 1 || file_length >= 1024) return target;
    size_t prefix = file_length - (sizeof(materials_suffix) - 1);
    if (file[prefix - 1] != '/' || strcasecmp(file + prefix, materials_suffix)) return target;

    float coordinates[4];
    const char keys[] = "xywh";
    for (int i = 0; i < 4; ++i) {
        char field[] = {keys[i], '\0'};
        GameString key = borrow_string(field, 1);
        coordinates[i] = directory_number(definition, &key);
        if (!(coordinates[i] >= 0 && coordinates[i] <= 256)) return target;
    }
    if (coordinates[2] == 0 || coordinates[3] == 0) return target;
    int offset[2];
    get_mod_sprite_offset(offset, renderer, materials_file);
    // A missing sheet resolves to (0, 0). The mobile packer only writes below
    // the base atlas, so sampling that offset would show an unrelated sprite.
    if (offset[0] < 0 || offset[1] <= 0) return target;
    uint32_t size[2];
    if (!read_material_sheet(materials_file, size) ||
        (coordinates[0] + coordinates[2]) * 32 > size[0] ||
        (coordinates[1] + coordinates[3]) * 32 > size[1]) return target;
    size_t name_size = strlen(icon_name) + 1;
    if (!icon) {
        icon = new_object(sizeof(*icon) + name_size);
        CalloutIcon **head = callout_icon_slot();
        *icon = (CalloutIcon){{0}, *head, toolbar};
        copy_bytes(icon->name, icon_name, name_size);
        *head = icon;
    }
    icon->tiles = (UVs){coordinates[0] + offset[0], coordinates[1] + offset[1],
                        coordinates[2], coordinates[3]};
    return target;
}

GameString *read_callout_icon(GameString *target, const GameString *name, const Directory *entry,
                             void *renderer, const GameString *materials_file) {
    return read_inline_icon(target, name, entry, renderer, materials_file, false);
}

GameString *read_toolbar_icon(GameString *target, const GameString *name, const Directory *entry,
                             void *renderer, const GameString *materials_file) {
    read_default_staff(name, entry);
    return read_inline_icon(target, name, entry, renderer, materials_file, true);
}

static UVs lookup_inline_icon(const GameString *name, bool toolbar) {
    for (const CalloutIcon *icon = *callout_icon_slot(); icon; icon = icon->next) {
        if (icon->toolbar == toolbar && !strcmp(icon->name, string_data(name))) return icon->tiles;
    }
    return (UVs){0};
}

const void *lookup_callout_label(const LanguageTable *language, const GameString *key) {
    if (language_has_phrase(language, key)) return language_lookup(language, key);
    const char prefix[] = "interfacecallout_";
    const size_t prefix_size = sizeof(prefix) - 1;
    const char *raw = string_data(key);
    size_t length = strlen(raw);
    if (length < prefix_size || length >= 256 || strncmp(raw, prefix, prefix_size)) {
        return language_lookup(language, key);
    }
    char alias[256];
    for (size_t i = 0; i <= length; ++i) {
        char ch = raw[i];
        alias[i] = ch >= 'A' && ch <= 'Z' ? ch + ('a' - 'A') : ch;
    }
    GameString canonical = borrow_string(alias, length);
    if (language_has_phrase(language, &canonical)) return language_lookup(language, &canonical);
    if (length > prefix_size + 5 && !strncmp(alias + prefix_size, "call_", 5)) {
        size_t short_length = length - 5;
        for (size_t i = prefix_size; i <= short_length; ++i) alias[i] = alias[i + 5];
        GameString desktop = borrow_string(alias, short_length);
        if (language_has_phrase(language, &desktop)) return language_lookup(language, &desktop);
    }
    return language_lookup(language, key);
}

/* The manager stores selections separately from the game's preferences.
 * The game may save those preferences while it is still using the old mods. */
void split_mod_preferences(const GameString *preferences, char separator, void *names) {
    const char filename[] = "patools-active-mods.txt";
    GameString path = {0};
    get_app_save_folder(&path);
    append_game_string(&path, filename, sizeof(filename) - 1);
    FILE *file = fopen(string_data(&path), "rb");
    if (path.short_size & 1) delete_object((void *)path.long_string.data);
    if (file) {
        char selection[4097];
        size_t size = fread(selection, 1, sizeof(selection), file);
        fclose(file);
        if (size < sizeof(selection)) {
            selection[size] = '\0';
            // A leading newline marks a line-separated list. Older lists use commas.
            if (selection[0] == '\n') {
                GameStringList *list = names;
                char *start = selection + 1;
                for (char *end = start; end <= selection + size; ++end) {
                    if (*end != '\n' && *end != '\0') continue;
                    if (end != start) {
                        GameString entry = {0};
                        assign_game_string(&entry, start, (unsigned)(end - start));
                        fast_list_insert(list, &entry, list->count);
                        if (entry.short_size & 1) delete_object((void *)entry.long_string.data);
                    }
                    if (!*end) break;
                    start = end + 1;
                }
            } else {
                GameString active = borrow_string(selection, size);
                split_game_string(&active, separator, names);
            }
            return;
        }
    }
    split_game_string(preferences, separator, names);
}

/* Keep the mod root as published by the engine. Prefer exact matches at each
 * level, and require a unique case-insensitive match when the spelling differs. */
static bool resolve_mod_path(char *resolved, size_t root_length) {
    for (char *segment = resolved + root_length; *segment;) {
        char *end = segment;
        while (*end && *end != '/') ++end;
        size_t length = end - segment;
        if (!length || (length == 1 && segment[0] == '.') ||
            (length == 2 && segment[0] == '.' && segment[1] == '.')) return false;
        char *separator = segment - 1;
        *separator = '\0';
        DIR *directory = opendir(resolved);
        *separator = '/';
        if (!directory) return false;

        char boundary = *end;
        *end = '\0';
        bool matched = false;
        bool ambiguous = false;
        bool exact = false;
        char alternative[256];
        struct dirent *entry;
        while ((entry = readdir(directory))) {
            if (!strcmp(entry->d_name, segment)) {
                exact = true;
                break;
            }
            if (length >= sizeof(alternative) || strcasecmp(entry->d_name, segment)) continue;
            if (matched) {
                ambiguous = true;
            } else {
                copy_bytes(alternative, entry->d_name, length);
                matched = true;
            }
        }
        closedir(directory);
        if (!exact && (!matched || ambiguous)) return false;
        *end = boundary;
        if (!exact) copy_bytes(segment, alternative, length);
        segment = boundary ? end + 1 : end;
    }
    return true;
}

void join_mod_file_path(GameString *result, const GameString *root, const GameString *relative) {
    concat_game_string(result, root, relative);
    const char *path = string_data(result);
    const char *asset = string_data(relative);
    size_t root_length = strlen(string_data(root));
    size_t length = strlen(path);
    char resolved[1024];
    if (strncmp(asset, "data/", 5) || !root_length || root_length >= length ||
        path[root_length - 1] != '/' || length >= sizeof(resolved) || disk_file_exists(result)) return;
    copy_bytes(resolved, path, length + 1);
    if (resolve_mod_path(resolved, root_length)) assign_game_string(result, resolved, length);
}

static bool png_dimensions(const GameString *path, uint32_t minimum, uint32_t dimensions[2]) {
    static const unsigned char signature[] = {137, 'P', 'N', 'G', 13, 10, 26, 10,
                                               0, 0, 0, 13, 'I', 'H', 'D', 'R'};
    unsigned char header[24];
    FILE *file = fopen(string_data(path), "rb");
    if (!file) return false;
    size_t size = fread(header, 1, sizeof(header), file);
    fclose(file);
    if (size != sizeof(header) || memcmp(header, signature, sizeof(signature))) return false;
    for (size_t offset = 16; offset < sizeof(header); offset += 4) {
        const unsigned char *dimension = header + offset;
        uint32_t value = (uint32_t)dimension[0] << 24 | (uint32_t)dimension[1] << 16 |
                         (uint32_t)dimension[2] << 8 | dimension[3];
        if (value < minimum || value > INT32_MAX) return false;
        if (dimensions) dimensions[(offset - 16) / 4] = value;
    }
    return true;
}

static bool has_png_dimensions(const GameString *path, uint32_t minimum) {
    return png_dimensions(path, minimum, NULL);
}

static bool read_material_sheet(const GameString *materials, uint32_t dimensions[2]) {
    static const char suffix[] = "data/materials.txt";
    static const char sheet[] = "data/sprites.png";
    const char *file = string_data(materials);
    char path[1024];
    size_t length = strlen(file);
    if (length <= sizeof(suffix) - 1 || length >= sizeof(path)) return false;
    size_t prefix = length - (sizeof(suffix) - 1);
    if (file[prefix - 1] != '/' || strcasecmp(file + prefix, suffix)) return false;
    copy_bytes(path, file, prefix);
    copy_bytes(path + prefix, sheet, sizeof(sheet));
    GameString candidate = borrow_string(path, prefix + sizeof(sheet) - 1);
    if (!disk_file_exists(&candidate)) {
        if (!resolve_mod_path(path, prefix)) return false;
        candidate = borrow_string(path, strlen(path));
    }
    return png_dimensions(&candidate, 1, dimensions);
}

static BinaryReader *open_mod_binary(void *filesystem, void *mods, const GameString *path,
                                     uint32_t minimum_png_dimension) {
    GameStringList files = {0};
    get_mod_file_paths(mods, path, &files, false);
    BinaryReader *reader = 0;
    for (int i = files.count; i > 0 && !reader; --i) {
        const GameString *candidate = &files.items[i - 1];
        if (minimum_png_dimension && !has_png_dimensions(candidate, minimum_png_dimension)) continue;
        reader = get_binary_reader(filesystem, candidate, false);
        if (minimum_png_dimension && reader) debug_log("PATools image: %s\n", string_data(candidate));
    }
    destroy_file_paths(&files);
    return reader;
}

BinaryReader *open_sound_sample(void *filesystem, const GameString *path, bool search_paths) {
    const ModList *mods = active_mod_system();
    const char *name = string_data(path);
    size_t length = strlen(name);
    if (mods && mods->count && length > 16 && length < 256 && !strcmp(name + length - 4, ".ogg")) {
        char wav[256];
        copy_bytes(wav, name, length - 4);
        copy_bytes(wav + length - 4, ".wav", 5);
        GameString alternate = borrow_string(wav, length);
        for (int i = mods->count; i > 0; --i) {
            // Keep the engine's mod eligibility and filename rules, with
            // both formats at the same priority within a single mod.
            ModList layer = {&mods->mods[i - 1], 1, 1};
            BinaryReader *reader = open_mod_binary(filesystem, &layer, path, 0);
            if (!reader) reader = open_mod_binary(filesystem, &layer, &alternate, 0);
            if (reader) return reader;
        }
    }
    return get_binary_reader(filesystem, path, search_paths);
}

const char *find_file_extension(const char *path, int separator) {
    const char *extension = 0;
    for (; *path; ++path) {
        if (*path == '/') extension = 0;
        else if (*path == separator) extension = path;
    }
    return extension;
}

int compare_sound_file_type(const GameString *extension, const char *type) {
    return strcasecmp(string_data(extension), type);
}

BinaryReader *open_mod_image(void *filesystem, const GameString *path, bool search_paths) {
    const char *name = string_data(path);
    size_t length = strlen(name);
    bool palette = !strcmp(name, "data/clothes.png") || !strcmp(name, "data/skin.png");
    bool logo = !strcasecmp(name, "data/palogo.png");
    bool png = length > 4 && !strcmp(name + length - 4, ".png");
    bool illustration = png && (!strncmp(name, "data/campaign/", 14) ||
                                !strncmp(name, "data/advisers/", 14) ||
                                !strncmp(name, "data/polaroids/", 15));
    static const char standalone[][27] = {
        "data/clipboard.png", "data/codex.png", "data/cloudyglow.bmp",
        "data/glow.bmp", "data/letter.png", "data/papersheet.bmp",
        "data/qualification.bmp", "data/sound.bmp", "data/starburst.bmp",
        "data/stripes.png", "data/tab.png", "data/target.png",
        "data/texture_corkboard.png", "data/viewcone.png"
    };
    bool texture = false;
    if (!palette && !logo && !illustration && !strncmp(name, "data/", 5)) {
        for (unsigned i = 0; i < sizeof(standalone) / sizeof(*standalone) && !texture; ++i) {
            texture = !strcmp(name, standalone[i]);
        }
    }
    if (palette || logo || illustration || texture) {
        void *mods = active_mod_system();
        if (mods) {
            // The biography generator samples quadrants of the clothing palette.
            uint32_t minimum = palette ? 2 : logo || (texture && png);
            BinaryReader *reader = open_mod_binary(filesystem, mods, path, minimum);
            if (reader) return reader;
        }
    }
    return get_binary_reader(filesystem, path, search_paths);
}

FILE *open_gallery_image(const char *name, const char *mode) {
    ModList *mods = active_mod_system();
    if (mods && mods->count && !strcmp(mode, "rb")) {
        const char *relative = !strncmp(name, "data/", 5) ? name + 5 : name;
        size_t length = strlen(relative);
        char logical[256];
        if (length > 14 && length < sizeof(logical) - 5 && !strncmp(relative, "polaroids/", 10) &&
            !strcmp(relative + length - 4, ".png")) {
            copy_bytes(logical, "data/", 5);
            copy_bytes(logical + 5, relative, length + 1);
            const GameString path = borrow_string(logical, length + 5);
            GameStringList files = {0};
            get_mod_file_paths(mods, &path, &files, false);
            FILE *file = NULL;
            for (int i = files.count; i > 0 && !file; --i) {
                const GameString *candidate = &files.items[i - 1];
                if (has_png_dimensions(candidate, 1)) file = fopen(string_data(candidate), mode);
            }
            destroy_file_paths(&files);
            if (file) return file;
        }
    }
    return fopen(name, mode);
}

TextReader *open_mod_text(void *filesystem, const GameString *path, bool search_paths) {
    ModList *mods = active_mod_system();
    if (mods && mods->count) {
        GameStringList files = {0};
        get_mod_file_paths(mods, path, &files, false);
        TextReader *reader = 0;
        for (int i = files.count; i > 0 && !reader; --i) {
            reader = get_text_reader(filesystem, &files.items[i - 1], false);
        }
        destroy_file_paths(&files);
        if (reader) return reader;
    }
    return get_text_reader(filesystem, path, search_paths);
}

TextReader *open_campaign_text_reader(void *filesystem, const GameString *path, bool search_paths) {
    if (!strncmp(string_data(path), "data/campaign/", sizeof("data/campaign/") - 1)) {
        return open_mod_text(filesystem, path, search_paths);
    }
    return get_text_reader(filesystem, path, search_paths);
}

void apply_mod_languages(LanguageTable *table, const GameString *locale) {
    const ModList *mods = active_mod_system();
    if (!table || !mods || !mods->count) return;
    static const char prefix[] = "data/language/";
    // Load desktop phrases first so the mod's shared and tablet text can override them.
    static const char filenames[][18] = {"d11.txt", "base-language.txt", "fullgame.txt", "tablets.txt"};
    const char *language = string_data(locale);
    size_t length = strlen(language);
    bool translated = length && length < 64 && strcmp(language, "english");
    for (int i = 0; i < mods->count; ++i) {
        ModList layer = {&mods->mods[i], 1, 1};
        for (unsigned level = 0; level <= (unsigned)translated; ++level) {
            for (unsigned j = 0; j < sizeof(filenames) / sizeof(*filenames); ++j) {
                char path[112];
                size_t offset = sizeof(prefix) - 1;
                copy_bytes(path, prefix, offset);
                if (level) {
                    copy_bytes(path + offset, language, length);
                    offset += length;
                    path[offset++] = '/';
                }
                size_t size = strlen(filenames[j]);
                copy_bytes(path + offset, filenames[j], size + 1);
                GameString relative = borrow_string(path, offset + size);
                GameStringList files = {0};
                get_mod_file_paths(&layer, &relative, &files, false);
                if (files.count) {
                    bool *overlay = language_overlay_slot();
                    *overlay = true;
                    load_language_table(table, files.items, false);
                    *overlay = false;
                }
                destroy_file_paths(&files);
            }
        }
    }
}

void list_campaign_scripts(void *filesystem, const GameString *directory, const GameString *pattern,
                           GameStringList *paths, bool full_path, bool strip_extension) {
    list_archive(filesystem, directory, pattern, paths, full_path, strip_extension);
    const char *relative = string_data(directory);
    const ModList *mods = active_mod_system();
    if (!mods || !full_path || strip_extension || strncmp(relative, "data/campaign/", 14)) return;
    size_t directory_length = strlen(relative);
    if (relative[directory_length - 1] != '/') return;

    for (int i = 0; i < mods->count; ++i) {
        const char *root = string_data(&mods->mods[i].path);
        size_t root_length = strlen(root);
        char mod_folder[1024];
        if (!root_length || root_length + directory_length + 2 > sizeof(mod_folder)) continue;
        copy_bytes(mod_folder, root, root_length);
        if (root[root_length - 1] != '/') mod_folder[root_length++] = '/';
        copy_bytes(mod_folder + root_length, relative, directory_length + 1);
        size_t prefix = root_length + directory_length;
        if (!resolve_mod_path(mod_folder, root_length)) continue;
        GameString folder = borrow_string(mod_folder, prefix);
        GameStringList files = {0};
        list_directory(&folder, pattern, &files, true);
        for (int j = 0; j < files.count; ++j) {
            const char *absolute = string_data(&files.items[j]);
            if (strncmp(absolute, mod_folder, prefix)) continue;
            const char *filename = absolute + prefix;
            size_t filename_length = strlen(filename);
            char logical[1024];
            if (directory_length + filename_length >= sizeof(logical)) continue;
            copy_bytes(logical, relative, directory_length);
            copy_bytes(logical + directory_length, filename, filename_length + 1);
            bool listed = false;
            for (int k = 0; k < paths->count && !listed; ++k) {
                listed = !strcasecmp(string_data(&paths->items[k]), logical);
            }
            if (!listed) {
                GameString entry = borrow_string(logical, strlen(logical));
                fast_list_insert(paths, &entry, paths->count);
            }
        }
        destroy_file_paths(&files);
    }
}

SampleGroup *replace_sample_group(void *manager, const char *name) {
    SampleGroup *group = find_sample_group(manager, name);
    if (!group) return create_sample_group(manager, name);
    destroy_sample_group(group);
    return group;
}

void merge_sound_event(SoundEventBlueprint *incoming, SoundEventBlueprint *existing, const GameString *file) {
    if (!existing || !strcmp(string_data(file), "data/sounds.txt")) {
        clear_sound_event(incoming);
        return;
    }
    if (!incoming->first) return;

    // Repeated event names in one object are separate instances. Replace the
    // previous layer's instances for those names and keep all incoming ones.
    int index = 0;
    for (SoundInstanceNode *node = existing->first; node;) {
        SoundInstanceNode *next = node->next;
        SoundInstanceBlueprint *instance = node->instance;
        SoundInstanceNode *replacement = incoming->first;
        while (replacement && strcasecmp(string_data(&replacement->instance->name), string_data(&instance->name))) {
            replacement = replacement->next;
        }
        if (replacement) {
            remove_sound_instance(existing, index);
            destroy_sound_instance(instance);
            delete_object(instance);
        } else {
            ++index;
        }
        node = next;
    }

    if (existing->last) existing->last->next = incoming->first;
    else existing->first = incoming->first;
    incoming->first->previous = existing->last;
    existing->last = incoming->last;
    existing->count += incoming->count;
    ++existing->revision;
    incoming->first = incoming->last = 0;
    incoming->count = 0;
}

static bool visible_rgba(uint32_t rgba) {
    return (rgba & 0xffffff) != 0xff00ff && (rgba >> 24) >= 9;
}

/* Ordered RGB dithering retains sub-step texture detail in the 17-spaced
 * RGBA4444 palette. Use one threshold for all channels to keep neutral grays
 * neutral. Alpha is rounded without dithering to avoid stippled silhouettes.
 * Palette colors (multiples of 17) remain exact at every pixel position. */
static inline __attribute__((always_inline)) uint16_t rgba4444(uint32_t rgba, unsigned x, unsigned y) {
    static const uint8_t bayer[64] = {
         0, 48, 12, 60,  3, 51, 15, 63,
        32, 16, 44, 28, 35, 19, 47, 31,
         8, 56,  4, 52, 11, 59,  7, 55,
        40, 24, 36, 20, 43, 27, 39, 23,
         2, 50, 14, 62,  1, 49, 13, 61,
        34, 18, 46, 30, 33, 17, 45, 29,
        10, 58,  6, 54,  9, 57,  5, 53,
        42, 26, 38, 22, 41, 25, 37, 21,
    };
    if (!visible_rgba(rgba)) return 0;
    unsigned threshold = (bayer[((y & 7) << 3) | (x & 7)] * 17 + 8) >> 6;
    /* Exact division by 17 for 0..271, without ARM's per-channel divide calls. */
    unsigned r = (((rgba & 255) + threshold) * 241) >> 12;
    unsigned g = ((((rgba >> 8) & 255) + threshold) * 241) >> 12;
    unsigned b = ((((rgba >> 16) & 255) + threshold) * 241) >> 12;
    unsigned a = (((rgba >> 24) + 8) * 241) >> 12;
    return (r << 12) | (g << 8) | (b << 4) | a;
}

/* Called by the native sprite packer's Blit shim. Coordinates are relative to
 * the PNG so atlas placement and rebuilding do not change the dither pattern. */
void copy_mod_sprite_pixels(uint16_t *destination, const Bitmap *png, int stride) {
    for (int row = 0; row < png->height; ++row, destination += stride) {
        const uint32_t *source = png->rows[row];
        for (int x = 0; x < png->width; ++x) {
            destination[x] = rgba4444(source[x], x, png->height - 1 - row);
        }
    }
}

static bool read_bitmap(Bitmap *image, BinaryReader *reader, const char *format) {
    if (!reader) return false;
    GameString extension = {.short_size = 6};
    copy_bytes((char *)&extension + 1, format, 4);
    decode_bitmap(image, reader, &extension);
    reader->vtable[1](reader);
    return true;
}

static bool read_png(Bitmap *image, BinaryReader *reader) {
    return read_bitmap(image, reader, "png");
}

static const char ui_atlas_path[] = "data/tablet/TextureAtlasses/TextureAtlasses.ui.csimage";
static const char ui_bank_path[] = "data/tablet/TextureAtlasses/TextureAtlasses.ui.spritebank";

static bool fit_icon(const Bitmap *png, const Rect *source, const Rect *frame, uint16_t *pixels, int stride);

static void apply_complaint_icons(Bitmap *atlas, Image *uploaded_ui, bool ui) {
    enum { columns = 21 };
    ModList *mods = active_mod_system();
    if (!mods || !mods->count) return;
    const int width = uploaded_ui ? uploaded_ui->width : atlas->width;
    const int height = uploaded_ui ? uploaded_ui->height : atlas->height;
    if (width <= 0 || height <= 0 || height > 4096 || (!ui && width != columns * height)) return;
    uint16_t *upload = NULL;
    int previous = 0;
    void *filesystem = game_filesystem();
    GameString png_path = borrow_string("data/complaints.png", sizeof("data/complaints.png") - 1);
    GameString bank_path = borrow_string("data/complaints.spritebank", sizeof("data/complaints.spritebank") - 1);
    GameString target_path = ui ? borrow_string(ui_bank_path, sizeof(ui_bank_path) - 1) : bank_path;
    // Native SpriteBank includes members beyond the renderer fields exposed here.
    union { SpriteBank bank; uint32_t words[23]; } stock, source;
    bool stock_loaded = false;
    for (int i = 0; i < mods->count; ++i) {
        ModList layer = {&mods->mods[i], 1, 1};
        GameStringList files = {0};
        get_mod_file_paths(&layer, &bank_path, &files, false);
        if (files.count || !ui) {
            Bitmap png;
            if (read_png(&png, open_mod_binary(filesystem, &layer, &png_path, 1))) {
                if (png.rows && png.height > 0 && png.height <= 4096 && png.width == columns * png.height) {
                    if (!stock_loaded) {
                        construct_sprite_bank(&stock.bank);
                        load_sprite_bank_path(&stock.bank, &target_path);
                        stock_loaded = true;
                    }
                    if (files.count) {
                        construct_sprite_bank(&source.bank);
                        load_sprite_bank_path(&source.bank, files.items);
                    }
                    bool changed = false;
                    for (int j = 0; j < stock.bank.count; ++j) {
                        if (!stock.bank.present[j]) continue;
                        const Sprite *target = stock.bank.sprites[j];
                        if (!target) continue;
                        const GameString *name = &target->name;
                        GameString alias;
                        if (ui) {
                            const char *key = string_data(name);
                            if (strncmp(key, "IconNeeds", 9) || !key[9]) continue;
                            key += 9;
                            if (!strcmp(key, "Cloathing")) key = "Clothing";
                            if (!strcmp(key, "Enviroment")) key = "Environment";
                            alias = borrow_string(key, strlen(key));
                            name = &alias;
                        }
                        const Sprite *icon = files.count ? lookup_sprite(&source.bank, name) : target;
                        if (!icon || icon->w != 1 || icon->h != 1 || icon->y != 0 || icon->x < 0 || icon->x >= columns) continue;
                        Rect frame = {target->x, target->y, target->w, target->h};
                        if (!ui) {
                            if (frame.x < 0 || frame.x >= columns || frame.y != 0 || frame.w != 1 || frame.h != 1) continue;
                            frame = (Rect){frame.x * height, 0, height, height};
                        }
                        if (frame.w <= 0 || frame.h <= 0 || frame.x < 0 || frame.y < 0 ||
                            frame.w > width - frame.x || frame.h > height - frame.y) continue;
                        Rect crop = {icon->x * png.height, 0, png.height, png.height};
                        int bottom = height - frame.y - frame.h;
                        if (uploaded_ui) {
                            if (frame.w > 128 || frame.h > 128) continue;
                            int stride = (frame.w + 1) & ~1;
                            if (!upload) {
                                upload = new_array(128 * 128 * sizeof(*upload));
                                gl_get_integer(0x8069, &previous);
                                gl_bind_texture(0x0de1, uploaded_ui->texture);
                            }
                            if (!fit_icon(&png, &crop, &frame, upload, stride)) continue;
                            upload_texture_region(0x0de1, 0, frame.x, bottom, frame.w, frame.h, 0x1908, 0x8033, upload);
                        } else if (ui) {
                            if (!fit_icon(&png, &crop, &frame, atlas->packed + bottom * width + frame.x, width)) continue;
                        } else {
                            unsigned tile = height;
                            for (unsigned y = 0; y < tile; ++y) {
                                uint16_t *dest = atlas->packed + y * width + frame.x;
                                const uint32_t *row = png.rows[y * png.height / tile] + crop.x;
                                for (unsigned x = 0; x < tile; ++x) {
                                    dest[x] = rgba4444(row[x * png.height / tile], x, tile - 1 - y);
                                }
                            }
                        }
                        changed = true;
                    }
                    if (changed) debug_log(ui ? "PATools needs panel icons: %s\n" : "PATools complaint icons: %s\n",
                                           files.count ? string_data(files.items) : string_data(&png_path));
                    if (files.count) destroy_sprite_bank(&source.bank);
                }
                bitmap_destroy(&png);
            }
        }
        destroy_file_paths(&files);
    }
    if (stock_loaded) destroy_sprite_bank(&stock.bank);
    if (upload) {
        if (uploaded_ui->mipmaps) gl_generate_mipmap(0x0de1);
        gl_bind_texture(0x0de1, previous);
        delete_array(upload);
    }
}

static const Rect main_title = {1, 457, 615, 254};
static const Rect new_game_title = {923, 1051, 507, 323};
static void apply_mod_sheet(Bitmap *atlas, void *filesystem, const char *name, const char *format,
                            int x, int y, int size);
static bool fit_icon(const Bitmap *png, const Rect *source, const Rect *frame, uint16_t *pixels, int stride) {
    if (png->rows && source->w > 0 && source->h > 0) {
        int left = source->x + source->w, bottom = source->y + source->h, right = 0, top = 0;
        for (int y = source->y; y < source->y + source->h; ++y) {
            for (int x = source->x; x < source->x + source->w; ++x) {
                if (!visible_rgba(png->rows[y][x])) continue;
                if (x < left) left = x;
                if (x + 1 > right) right = x + 1;
                if (y < bottom) bottom = y;
                top = y + 1;
            }
        }
        if (right > left && top > bottom) {
            int source_w = right - left, source_h = top - bottom;
            float scale_x = (float)frame->w / source_w, scale_y = (float)frame->h / source_h;
            float scale = scale_x < scale_y ? scale_x : scale_y;
            int w = (int)(source_w * scale + 0.5f), h = (int)(source_h * scale + 0.5f);
            if (w < 1) w = 1;
            if (h < 1) h = 1;
            int inset_x = (frame->w - w) / 2;
            int inset_y = (frame->h - h) / 2;
            for (int y = 0; y < frame->h; ++y) {
                uint16_t *dst = pixels + y * stride;
                zero_bytes(dst, frame->w * sizeof(*dst));
                int row = y - inset_y;
                if (row < 0 || row >= h) continue;
                const uint32_t *src = png->rows[bottom + (unsigned)row * source_h / h] + left;
                for (int x = 0; x < w; ++x) {
                    dst[inset_x + x] = rgba4444(src[(unsigned)x * source_w / w], x, h - 1 - row);
                }
            }
            return true;
        }
    }
    return false;
}

static bool render_menu_title(const Rect *frame, uint16_t *pixels, int stride) {
    ModList *mods = active_mod_system();
    if (!mods || !mods->count) return false;
    GameString logo = borrow_string("data/PAlogo.png", sizeof("data/PAlogo.png") - 1);
    Bitmap png;
    if (!read_png(&png, open_mod_binary(game_filesystem(), mods, &logo, 1))) return false;
    Rect source = {0, 0, png.width, png.height};
    bool drawn = fit_icon(&png, &source, frame, pixels, stride);
    bitmap_destroy(&png);
    return drawn;
}

void decode_mod_atlas(Bitmap *atlas, BinaryReader *reader, const GameString *extension, const GameString *path) {
    decode_bitmap(atlas, reader, extension);
    if (atlas->format != 0x8033 || !atlas->packed) return;
    const char *name = string_data(path);
    if (!strcmp(name, "data/complaints.csimage")) {
        apply_complaint_icons(atlas, NULL, false);
        return;
    }
    if (!strcmp(name, "data/tileset.csimage") || !strcmp(name, "tileset.csimage")) {
        if (atlas->width == 2048 && atlas->height == 2048) {
            apply_mod_sheet(atlas, game_filesystem(), "data/tileset.png", "png", 0, 0, 2048);
        }
        return;
    }
    if (!strcmp(name, "effects.csimage") || !strcmp(name, "data/effects.csimage")) {
        if (atlas->width == 512 && atlas->height == 512) {
            apply_mod_sheet(atlas, game_filesystem(), "data/effects.bmp", "bmp", 0, 0, 512);
        }
        return;
    }
    bool main = !strcmp(name, ui_atlas_path);
    if (main) apply_complaint_icons(atlas, NULL, true);
    const Rect *frame = main ? &main_title :
        !strcmp(name, "data/tablet/TextureAtlasses/TextureAtlasses.pausemenu.csimage") ? &new_game_title : NULL;
    if (frame && frame->x + frame->w <= atlas->width && frame->y + frame->h <= atlas->height &&
        render_menu_title(frame, atlas->packed + (atlas->height - frame->y - frame->h) * atlas->width + frame->x,
                          atlas->width)) {
        debug_log("PATools menu title: %s\n", name);
    }
}

bool track_menu_title(Image *image, bool mipmaps, bool pink, bool keep, bool linear) {
    bool ready = make_image_texture(image, mipmaps, pink, keep, linear);
    if (ready && !active_mod_system() && !strcmp(string_data(&image->path), ui_atlas_path)) {
        *menu_title_image_slot() = image;
    }
    return ready;
}

void refresh_menu_title(void) {
    Image **slot = menu_title_image_slot();
    Image *image = *slot;
    *slot = NULL;
    const Rect *frame = &main_title;
    if (!image || image->texture < 0 || frame->x + frame->w > image->width || frame->y + frame->h > image->height) return;
    apply_complaint_icons(NULL, image, true);
    // An even row stride keeps the stock GL unpack alignment.
    int stride = (frame->w + 1) & ~1;
    uint16_t *pixels = new_array(stride * frame->h * sizeof(*pixels));
    if (render_menu_title(frame, pixels, stride)) {
        int previous;
        gl_get_integer(0x8069, &previous);
        gl_bind_texture(0x0de1, image->texture);
        upload_texture_region(0x0de1, 0, frame->x, image->height - frame->y - frame->h,
                              frame->w, frame->h, 0x1908, 0x8033, pixels);
        if (image->mipmaps) gl_generate_mipmap(0x0de1);
        gl_bind_texture(0x0de1, previous);
        debug_log("PATools menu title: %s\n", ui_atlas_path);
    }
    delete_array(pixels);
}


static void apply_mod_sheet(Bitmap *atlas, void *filesystem, const char *name, const char *format,
                            int x, int y, int size) {
    ModList *mods = active_mod_system();
    if (!mods || !mods->count) return;
    GameString path = borrow_string(name, strlen(name));
    GameStringList files = {0};
    get_mod_file_paths(mods, &path, &files, false);
    Bitmap baseline;
    if (files.count && read_bitmap(&baseline, get_binary_reader(filesystem, &path, false), format)) {
        if (baseline.rows && baseline.width == size && baseline.height == size) {
            for (int i = 0; i < files.count; ++i) {
                Bitmap sheet;
                const GameString *file = &files.items[i];
                if (!read_bitmap(&sheet, get_binary_reader(filesystem, file, false), format)) continue;
                if (sheet.rows && sheet.width == size && sheet.height == size) {
                    uint16_t *destination = atlas->packed + x + (atlas->height - y - size) * atlas->width;
                    for (int row = 0; row < size; ++row, destination += atlas->width) {
                        const uint32_t *original = baseline.rows[row];
                        const uint32_t *replacement = sheet.rows[row];
                        for (int column = 0; column < size; ++column) {
                            uint32_t old = original[column], pixel = replacement[column];
                            if (old != pixel && (old | pixel) >> 24) {
                                destination[column] = rgba4444(pixel, column, size - 1 - row);
                            }
                        }
                    }
                    debug_log("PATools atlas sheet: %s\n", string_data(file));
                } else {
                    debug_log("PATools atlas sheet has incompatible dimensions: %s\n", string_data(file));
                }
                bitmap_destroy(&sheet);
            }
        }
        bitmap_destroy(&baseline);
    }
    destroy_file_paths(&files);
}

/* Desktop mods keep their quickbuilds in data/prefabs_dlc.txt. The mobile
 * engine only asks for data/prefabs.txt, so list the DLC file as well. */
void list_prefab_files(const ModList *mods, const GameString *path, GameStringList *files, bool include_base) {
    static const char dlc_path[] = "data/prefabs_dlc.txt";
    if (include_base) fast_list_insert(files, path, files->count);
    for (int i = 0; i < mods->count; ++i) {
        ModList layer = {&mods->mods[i], 1, 1};
        get_mod_file_paths(&layer, path, files, false);
        GameString dlc = borrow_string(dlc_path, sizeof(dlc_path) - 1);
        get_mod_file_paths(&layer, &dlc, files, false);
    }
}

void apply_mod_composite_sheets(Bitmap *atlas, void *filesystem) {
    enum { sheet_size = 2048 };
    static const struct {
        char path[32];
        int x, y;
    } sheets[] = {
        {"data/objects.png", 0, 0},
        {"data/people.png", 0, sheet_size},
        {"data/special-entities.png", sheet_size, 0}
    };
    if (!atlas->packed || atlas->width != 4096 || atlas->height < 4096) return;
    for (unsigned n = 0; n < sizeof(sheets) / sizeof(*sheets); ++n) {
        apply_mod_sheet(atlas, filesystem, sheets[n].path, "png", sheets[n].x, sheets[n].y, sheet_size);
    }
}

static void copy_frame(Bitmap *atlas, const Bitmap *png, const Rect *frame, int left, int top, int row) {
    int src_x = (frame->x - left) * 32;
    int src_y = (frame->y - top + row) * 32;
    int width = frame->w * 32;
    int height = frame->h * 32;
    uint16_t *dst = atlas->packed +
        (atlas->height - (frame->y + frame->h) * 32) * atlas->width + frame->x * 32;
    for (int y = 0; y < height; ++y, dst += atlas->width) {
        const uint32_t *src = png->rows[png->height - src_y - height + y] + src_x;
        for (int x = 0; x < width; ++x) {
            dst[x] = rgba4444(src[x], src_x + x, src_y + height - 1 - y);
        }
    }
}

static void read_frames(const Sprite *sprite, Rect *frames) {
    const float d = 0.70710677f;
    static const float directions[][2] = {
        {0, 1}, {-d, d}, {-1, 0}, {-d, -d}, {0, -1}, {d, -d}, {1, 0}, {d, d}
    };
    for (int i = 0; i < 8; ++i) {
        Rect *frame = &frames[i];
        int orientation, w = sprite->w, h = sprite->h;
        sprite_rect(sprite, directions[i], &orientation, &frame->x, &frame->y,
                    &frame->w, &frame->h, &w, &h);
    }
}

static bool frame_fits(const Rect *frame, int columns, int rows) {
    return frame->x >= 0 && frame->y >= 0 && frame->w > 0 && frame->h > 0 &&
        frame->x < columns && frame->y < rows &&
        frame->w <= columns - frame->x && frame->h <= rows - frame->y;
}

/* The tablet build menu draws stock objects from a separate atlas. Use the
 * composite image when the selected sprite was added by mod materials. */
void *make_object_preview(void *drawable, const TextureRef *texture, const void *atlas,
                          const GameString *name, int object_id, int mode,
                          const void *colour, const UVs *uv) {
    int stock_count;
    UiTexture **preview;
    SpriteBank *bank = object_preview_state(&stock_count, &preview);
    if (bank && bank->image && bank->image->texture >= 0 && stock_count > 0) {
        const Sprite *sprite = 0;
        UVs tiles = {0};
        if (mode == MODE_EMERGENCIES && object_id > 0 && object_id < FIRST_SPECIAL_ACTION) {
            const CalloutTemplate *callout = get_callout_template(object_id);
            tiles = lookup_inline_icon(&callout->name, false);
            // A mod callout without its own icon shows the unit it summons.
            if (tiles.w == 0 && is_mod_callout(&callout->name) && callout->entity > 0) {
                const ObjectTemplate *entity = get_object_template(callout->entity);
                if (entity) {
                    int id = entity->toolbar_sprite >= 0 ? entity->toolbar_sprite : entity->sprite;
                    if (id >= 0 && id < bank->count && bank->present[id]) sprite = bank->sprites[id];
                }
            }
        } else if ((mode == MODE_OBJECTS || mode == MODE_STAFF || mode == 2 || mode == 7)
                   && object_id >= 0 && object_id < FIRST_SPECIAL_ACTION) {
            const ObjectTemplate *object = get_object_template(object_id);
            if (object) {
                tiles = lookup_inline_icon(&object->name, true);
                int id = object->toolbar_sprite >= 0 ? object->toolbar_sprite : object->sprite;
                if (tiles.w == 0 && id >= stock_count && id < bank->count && bank->present[id]) {
                    sprite = bank->sprites[id];
                }
            }
        }
        if (tiles.w == 0 && !sprite) {
            const Sprite *named = lookup_sprite(bank, name);
            for (int i = stock_count; named && i < bank->count; ++i) {
                if (bank->present[i] && bank->sprites[i] == named) {
                    sprite = named;
                    break;
                }
            }
        }
        if (sprite) tiles = (UVs){sprite->x, sprite->y, sprite->w, sprite->h};
        const Image *image = bank->image;
        if (tiles.x >= 0 && tiles.y >= 0 && tiles.w * 32 > 1 && tiles.h * 32 > 1
                && (tiles.x + tiles.w) * 32 <= image->width && (tiles.y + tiles.h) * 32 <= image->height) {
            if (!*preview) create_ui_texture(preview);
            int dimensions[] = {image->width, image->height};
            build_ui_texture(*preview, dimensions);
            TextureRef live = {*preview, 0};
            UVs crop = {
                (tiles.x * 32 + 0.5f) / image->width,
                (tiles.y * 32 + 0.5f) / image->height,
                (tiles.w * 32 - 1.0f) / image->width,
                (tiles.h * 32 - 1.0f) / image->height,
            };
            return make_texture_drawable(drawable, &live, colour, &crop);
        }
    }
    return make_atlas_drawable(drawable, texture, atlas, name, colour, uv);
}

void draw_preview(void *canvas, const void *matrix, const float *size, const void *offset, float depth,
                  const TextureRef *texture, const void *colour, int anchor, const UVs *uv) {
    int stock_count;
    UiTexture **preview;
    SpriteBank *bank = object_preview_state(&stock_count, &preview);
    if (bank && *preview && texture->texture == *preview) {
        // Undo the half-texel inset at each edge when computing the sprite's aspect ratio.
        float width = uv->w * bank->image->width + 1.0f;
        float height = uv->h * bank->image->height + 1.0f;
        float scale_x = size[0] / width;
        float scale_y = size[1] / height;
        float scale = scale_x < scale_y ? scale_x : scale_y;
        float fitted[] = {width * scale, height * scale};
        draw_sprite_bank_box(canvas, matrix, fitted, offset, depth, bank, uv, colour, anchor);
    } else {
        draw_texture_box(canvas, matrix, size, offset, depth, texture, colour, anchor);
    }
}

/* The death renderer uses the fourth tile of square rotation-1 bodies.
 * It is absent from the directional bank. Record the stock duplicate only
 * when the tile is unclaimed and its silhouette matches the front frame. */
static uint8_t *find_fallen_frames(const SpriteBank *bank) {
    Bitmap *atlas = bank->image->bitmap;
    int columns = atlas->width / 32, rows = atlas->height / 32;
    if (bank->count <= 0 || columns <= 0 || rows <= 0 || columns > 256 || rows > 256) return 0;
    uint8_t *fallen = new_array(bank->count);
    uint8_t *reserved = new_array(columns * rows);
    zero_bytes(fallen, bank->count);
    zero_bytes(reserved, columns * rows);
    for (int i = 0; i < bank->count; ++i) {
        if (!bank->present[i] || !bank->sprites[i]) continue;
        Rect frames[8];
        read_frames(bank->sprites[i], frames);
        for (int n = 0; n < 8; ++n) {
            const Rect *frame = &frames[n];
            if (!frame_fits(frame, columns, rows)) continue;
            for (int y = frame->y; y < frame->y + frame->h; ++y) {
                for (int x = frame->x; x < frame->x + frame->w; ++x) reserved[y * columns + x] = 1;
            }
        }
    }
    for (int i = 0; i < bank->count; ++i) {
        if (!bank->present[i] || !bank->sprites[i]) continue;
        const Sprite *sprite = bank->sprites[i];
        if (sprite->rotation != 1 || sprite->w != sprite->h || sprite->w <= 0 || sprite->w > columns / 4) continue;
        Rect front = {sprite->x, sprite->y, sprite->w, sprite->h};
        Rect death = {sprite->x + sprite->w * 3, sprite->y, sprite->w, sprite->h};
        if (!frame_fits(&front, columns, rows) || !frame_fits(&death, columns, rows)) continue;
        bool free = true;
        for (int y = death.y; y < death.y + death.h; ++y) {
            for (int x = death.x; x < death.x + death.w; ++x) free &= !reserved[y * columns + x];
        }
        if (!free) continue;
        int visible = 0, mismatch = 0;
        const uint16_t *line = atlas->packed +
            (atlas->height - (front.y + front.h) * 32) * atlas->width + front.x * 32;
        for (int y = 0; y < front.h * 32; ++y, line += atlas->width) {
            for (int x = 0; x < front.w * 32; ++x) {
                uint16_t a = line[x], b = line[x + sprite->w * 96];
                if (!(a & 15) && !(b & 15)) continue;
                ++visible;
                int r = (a >> 12) - (b >> 12), g = ((a >> 8) & 15) - ((b >> 8) & 15);
                int blue = ((a >> 4) & 15) - ((b >> 4) & 15);
                mismatch += !(a & 15) || !(b & 15) || r * r + g * g + blue * blue > 12;
            }
        }
        fallen[i] = visible > 0 && mismatch * 8 <= visible;
    }
    delete_array(reserved);
    return fallen;
}

static bool has_fallen_frame(const SpriteBank *bank, const Sprite *sprite, const uint8_t *fallen) {
    if (!fallen) return false;
    for (int i = 0; i < bank->count; ++i) {
        if (bank->present[i] && bank->sprites[i] == sprite) return fallen[i];
    }
    return false;
}

static bool replace_row(Bitmap *atlas, const Bitmap *png, const Sprite *sprite, int row, bool fallen) {
    Rect frames[9];
    int count = 8;
    read_frames(sprite, frames);
    if (fallen && png->width / 32 >= sprite->w * 4) {
        frames[count++] = (Rect){sprite->x + sprite->w * 3, sprite->y, sprite->w, sprite->h};
    }
    int left = atlas->width / 32, top = atlas->height / 32;
    int right = 0, bottom = 0;
    for (int i = 0; i < count; ++i) {
        const Rect *frame = &frames[i];
        if (!frame_fits(frame, atlas->width / 32, atlas->height / 32)) return false;
        int x = frame->x, y = frame->y, r = x + frame->w, b = y + frame->h;
        if (x < left) left = x;
        if (y < top) top = y;
        if (r > right) right = r;
        if (b > bottom) bottom = b;
    }
    if ((right - left) * 32 > png->width || (bottom - top + row) * 32 > png->height) return false;
    for (int i = 0; i < count; ++i) {
        int earlier = 0;
        while (earlier < i && memcmp(&frames[i], &frames[earlier], sizeof(Rect))) ++earlier;
        if (earlier == i) copy_frame(atlas, png, &frames[i], left, top, row);
    }
    return true;
}

/* The desktop can group stacked variants in one PNG. Match every extra row
 * to a corresponding numbered sprite with the same geometry in the bank. */
static void replace_variants(SpriteBank *bank, const Bitmap *png, const Sprite *first,
                             char *name, unsigned length, const uint8_t *fallen) {
    if (first->h <= 0 || first->h > png->height / 64 || length > 252 ||
        (length && name[length - 1] >= '0' && name[length - 1] <= '9')) return;
    for (int variant = 2; variant <= 99 && variant * first->h <= png->height / 32; ++variant) {
        unsigned end = length;
        if (variant >= 10) name[end++] = '0' + variant / 10;
        name[end++] = '0' + variant % 10;
        name[end] = 0;
        GameString key = borrow_string(name, end);
        const Sprite *next = lookup_sprite(bank, &key);
        if (!next || next->rotation != first->rotation || next->w != first->w ||
            next->h != first->h || next->x != first->x || next->y != first->y + (variant - 1) * first->h ||
            !replace_row(bank->image->bitmap, png, next, (variant - 1) * first->h,
                         has_fallen_frame(bank, next, fallen))) break;
    }
    name[length] = 0;
}

static bool replace_sprite(SpriteBank *bank, void *filesystem, char *path, unsigned end, char *name,
                           unsigned name_length, const uint8_t *fallen) {
    name[name_length] = 0;
    GameString key = borrow_string(name, name_length);
    const Sprite *sprite = lookup_sprite(bank, &key);
    if (!sprite) return false;
    GameString path_string = borrow_string(path, end);
    Bitmap png;
    if (!read_png(&png, get_binary_reader(filesystem, &path_string, false))) return false;
    bool changed = false;
    if (png.rows && png.width > 0 && png.height > 0 && png.width % 32 == 0 && png.height % 32 == 0) {
        Bitmap *atlas = bank->image->bitmap;
        changed = replace_row(atlas, &png, sprite, 0, has_fallen_frame(bank, sprite, fallen));
        if (changed) {
            replace_variants(bank, &png, sprite, name, name_length, fallen);
            debug_log("Loaded mod sprite replacement %s", name);
        }
    }
    bitmap_destroy(&png);
    return changed;
}

static bool apply_replacement_files(SpriteBank *bank, void *filesystem, DIR *folder, char *path,
                                    unsigned end, const uint8_t *fallen, bool numbered) {
    static const char prefix[] = "default_";
    const unsigned offset = sizeof(prefix) - 1;
    char name[256];
    bool changed = false;
    const struct dirent *entry;
    while ((entry = readdir(folder))) {
        const char *file = entry->d_name;
        unsigned length = strlen(file);
        if (length <= offset + 4 || length >= sizeof(name) || strncasecmp(file, prefix, offset) ||
            strcasecmp(file + length - 4, ".png")) continue;
        char last = file[length - 5];
        if ((last >= '0' && last <= '9') != numbered) continue;
        unsigned name_length = length - offset - 4;
        copy_bytes(name, file + offset, name_length);
        if (strncmp(file, prefix, offset) || strcmp(file + length - 4, ".png")) {
            copy_bytes(path + end, prefix, offset);
            copy_bytes(path + end + offset, name, name_length);
            copy_bytes(path + end + length - 4, ".png", 5);
            if (!resolve_mod_path(path, end) || strcmp(path + end, file)) continue;
        }
        copy_bytes(path + end, file, length + 1);
        changed |= replace_sprite(bank, filesystem, path, end + length, name, name_length, fallen);
    }
    closedir(folder);
    path[end] = '\0';
    return changed;
}

void apply_mod_sprite_replacements(SpriteBank *bank, const ModList *list, void *filesystem) {
    static const char directory[] = "data/sprite_replacement/default/";
    Image *image = bank->image;
    if (!list || !list->count || !image || !image->bitmap ||
        image->bitmap->format != 0x8033 || !image->bitmap->packed) return;
    bool changed = false;
    uint8_t *fallen = 0;
    for (int i = 0; i < list->count; ++i) {
        char path[1024];
        const char *root = string_data(&list->mods[i].path);
        unsigned end = strlen(root);
        if (!end || end + sizeof(directory) + 256 >= sizeof(path)) continue;
        copy_bytes(path, root, end);
        if (path[end - 1] != '/') path[end++] = '/';
        unsigned root_length = end;
        copy_bytes(path + end, directory, sizeof(directory));
        end += sizeof(directory) - 1;
        DIR *folder = opendir(path);
        if (!folder && resolve_mod_path(path, root_length)) folder = opendir(path);
        if (!folder) continue;
        if (!fallen) fallen = find_fallen_frames(bank);
        changed |= apply_replacement_files(bank, filesystem, folder, path, end, fallen, false);
        // Explicit numbered files override the same row in a stacked PNG.
        folder = opendir(path);
        if (folder) changed |= apply_replacement_files(bank, filesystem, folder, path, end, fallen, true);
    }
    if (fallen) delete_array(fallen);
    if (changed && image->texture >= 0) {
        upload_bitmap(image->bitmap, image->mipmaps, image->texture, image->linear_filter);
    }
}
