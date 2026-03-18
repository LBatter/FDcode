CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c99
LDFLAGS = -lpthread
TARGET = cache_monitor
SOURCE = cache_monitor.c

.PHONY: all clean install

all: $(TARGET)

$(TARGET): $(SOURCE)
	$(CC) $(CFLAGS) -o $(TARGET) $(SOURCE) $(LDFLAGS)

clean:
	rm -f $(TARGET) *.csv

install: $(TARGET)
	sudo cp $(TARGET) /usr/local/bin/
	sudo chmod +x /usr/local/bin/$(TARGET)

help:
	@echo "使用方法:"
	@echo "  make          - 编译程序"
	@echo "  make clean    - 清理编译文件和CSV输出"
	@echo "  make install  - 安装到系统路径"
	@echo "  make help     - 显示此帮助信息"
	@echo ""
	@echo "程序使用:"
	@echo "  sudo ./$(TARGET)                    - 默认监控10秒，100微秒间隔"
	@echo "  sudo ./$(TARGET) 30                 - 监控30秒，100微秒间隔"
	@echo "  sudo ./$(TARGET) 30 50              - 监控30秒，50微秒间隔"
