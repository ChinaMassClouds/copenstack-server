NAME = fedora-logos
XML = backgrounds/desktop-backgrounds-fedora.xml

all: update-po bootloader/fedora.icns

bootloader/fedora.icns: pixmaps/fedora-logo-sprite.svg
	convert -background none -resize 128x128 pixmaps/fedora-logo-sprite.svg pixmaps/fedora-logo-sprite.png
	png2icns bootloader/fedora.icns pixmaps/fedora-logo-sprite.png

update-po:
	@echo "updating pot files..."
	sed -e "s/_name/name/g" $(XML).in > $(XML)
	# FIXME need to handle translations
	#
	#( cd po && intltool-update --gettext-package=$(NAME) --pot )
	#@echo "merging existing po files to xml..."
	#intltool-merge -x po $(XML).in $(XML)
