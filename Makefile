WWW = /proj/web-cxc/htdocs/contrib/pyyaks

.PHONY: doc dist

dist:
	python setup.py sdist

doc:
	cd doc; \
	make html

install:
	rsync -av doc/_build/html/ $(WWW)/
	rsync -av dist/pyyaks-*.tar.gz $(WWW)/downloads/
