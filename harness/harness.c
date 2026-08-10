#include <stdio.h>
#include <stdlib.h>
#include "../target/parson/parson.h"

/* Read entire file into memory */
char *read_file(const char *filename) {
    FILE *fp = fopen(filename, "rb");
    if (!fp) {
        return NULL;
    }

    fseek(fp, 0, SEEK_END);
    long length = ftell(fp);
    rewind(fp);

    char *buffer = (char *)malloc(length + 1);
    if (!buffer) {
        fclose(fp);
        return NULL;
    }

    fread(buffer, 1, length, fp);
    buffer[length] = '\0';

    fclose(fp);
    return buffer;
}

int main(int argc, char *argv[]) {

    if (argc != 2) {
        fprintf(stderr, "Usage: %s <json_file>\n", argv[0]);
        return 1;
    }

    char *input = read_file(argv[1]);

    if (input == NULL) {
        fprintf(stderr, "Cannot read file.\n");
        return 1;
    }

    JSON_Value *value = json_parse_string(input);

    if (value == NULL) {
        printf("INVALID JSON\n");
    } else {
        printf("VALID JSON\n");
        json_value_free(value);
    }

    free(input);

    return 0;
}