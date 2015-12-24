ANACONDADATADIR = /usr/share/anaconda
ANACONDABOOTDIR = $(ANACONDADATADIR)/boot

all: 
	@echo "Nothing to do."

#splash.lss: syslinux-splash.png
#	./splashtolss.sh syslinux-splash.png splash.lss

install:
	@if [ "$(DESTDIR)" = "" ]; then \
		echo " "; \
		echo "ERROR: A destdir is required"; \
		exit 1; \
	fi

	mkdir -p $(DESTDIR)/$(ANACONDADATADIR)
	mkdir -p $(DESTDIR)/$(ANACONDABOOTDIR)
	mkdir -p $(DESTDIR)/$(ANACONDADATADIR)/pixmaps/rnotes/en

	install -m 644 splash.lss $(DESTDIR)/$(ANACONDABOOTDIR)
	install -m 644 syslinux-splash.png $(DESTDIR)/$(ANACONDABOOTDIR)/syslinux-splash.png
	# install -m 755 splashtolss.sh $(DESTDIR)/$(ANACONDADATADIR)
	install -m 644 -t $(DESTDIR)/$(ANACONDADATADIR)/pixmaps/rnotes/en rnotes/en/*
	install -m 644 -t $(DESTDIR)/$(ANACONDADATADIR)/pixmaps theme/*

clean:
	rm -f splash.lss
