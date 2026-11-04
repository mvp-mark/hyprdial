# COPR "make srpm" builds: COPR runs `make -f .copr/Makefile srpm outdir=... spec=...` as root, with network.
# The source RPM is made from packaging/rpm/hyprdial.spec and the GitHub tarball of its Version.
SPEC = packaging/rpm/hyprdial.spec

srpm:
	dnf -y install rpmdevtools rpm-build
	spectool -g -C $(outdir) $(SPEC)
	rpmbuild -bs --define "_sourcedir $(outdir)" --define "_srcrpmdir $(outdir)" $(SPEC)
