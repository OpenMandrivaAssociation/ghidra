%global __jar_repack 0
%global __requires_exclude_from ^%{_datadir}/ghidra/.*\\.jar$
%global __provides_exclude_from ^%{_datadir}/ghidra/.*\\.jar$
# Ghidra ships its own Python tree, including Jython. Do not byte-compile it.
%global _python_bytecompile_extra 0
# Natives are built without DWARF. find-debuginfo then writes an empty
# debugsource file list and rpmbuild aborts.
%global debug_package %{nil}

Name:		ghidra
Version:	12.2
Release:	1
Summary:	Software reverse engineering framework
Group:		Development/Tools
License:	ASL 2.0 and LGPLv2+
URL:		https://ghidra-sre.org/
Source0:	https://github.com/NationalSecurityAgency/ghidra/archive/refs/tags/Ghidra_%{version}_build.tar.gz
# Vendored dependency tree from Ghidra's fetchDependencies, with
# dependencies/downloads, foreign-arch wheels, and prebuilt Z3 libraries
# removed. FunctionID databases, the YAJSW server archive, BSim's PostgreSQL
# sources, and the Python sdists stay. YAJSW jars contain prebuilt natives.
Source1:	ghidra-%{version}-dependencies.tar.xz
# Maven artifacts resolved while building Ghidra. They are not in the
# OpenMandriva repositories, and the package build has no network. JNA and
# jline-native carry their own multi-arch natives inside the jars.
Source2:	ghidra-%{version}-gradle-cache.tar.xz
Source3:	https://github.com/protocolbuffers/protobuf/releases/download/v31.0/protobuf-31.0.tar.gz
Source4:	https://github.com/abseil/abseil-cpp/releases/download/20250127.0/abseil-cpp-20250127.0.tar.gz
Source5:	https://github.com/Z3Prover/z3/archive/refs/tags/z3-4.13.3.tar.gz
Patch0:		ghidra-%{version}-openmandriva.patch

BuildRequires:	clang
BuildRequires:	cmake
BuildRequires:	gradle >= 9.1
BuildRequires:	java-25-openjdk-devel
BuildRequires:	ninja
BuildRequires:	patchelf
BuildRequires:	pkgconfig(python3)
BuildRequires:	pkgconfig(z3)
BuildRequires:	pkgconfig(zlib)
BuildRequires:	python
BuildRequires:	python-pip
BuildRequires:	python-setuptools
BuildRequires:	python-wheel
BuildRequires:	unzip

# Launch scripts look for a JDK (javac) under /usr/lib/jvm.
Requires:	java-devel >= 25
Requires:	python
Requires:	python-pip
# libz3java.so is stored inside the SymbolicSummaryZ3 extension zip, so the
# ELF generator does not see it. It is linked to this system SONAME.
Requires:	libz3.so.4.13()(64bit)

%description
Ghidra is a software reverse engineering framework. It disassembles and
decompiles native programs, debugs them, and scripts the results.

Natives are compiled with clang. The decompiler's sleigh compiler links the
system zlib, and the Z3 JNI links the system libz3. protoc 31 is built from
source during the package build so generated Java matches the protobuf
version Ghidra pins. The Ghidra Server is installed from the upstream YAJSW
archive.

%prep
%autosetup -n ghidra-Ghidra_%{version}_build -p1

python - << 'PY'
from pathlib import Path
p = Path("Ghidra/application.properties")
text = p.read_text()
repls = {
    "application.release.name": "PUBLIC",
    "application.build.date": "2026-Oct-16 0000 UTC",
    "application.build.date.short": "20261016",
    "application.revision.ghidra": "8ca9077040cc43cd790babcfccf19475622a3e9a",
}
lines = text.splitlines()
seen = set()
out = []
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        key = line.split("=", 1)[0]
        if key in repls:
            out.append(key + "=" + repls[key])
            seen.add(key)
            continue
    out.append(line)
for key, value in repls.items():
    if key not in seen:
        out.append(key + "=" + value)
p.write_text("\n".join(out) + "\n")
PY

tar -xf %{SOURCE1}
tar -xf %{SOURCE3} -C %{_builddir}
tar -xf %{SOURCE4} -C %{_builddir}
tar -xf %{SOURCE5} -C %{_builddir}
mkdir -p %{_builddir}/gradle-home
tar -xf %{SOURCE2} -C %{_builddir}/gradle-home

%build
cd %{_builddir}/ghidra-Ghidra_%{version}_build

export JAVA_HOME=/usr/lib/jvm/java-25-openjdk
export PATH="${JAVA_HOME}/bin:${PATH}"
export CC=clang
export CXX=clang++
export GRADLE_USER_HOME=%{_builddir}/gradle-home
export GRADLE_OPTS="-Duser.language=en -Duser.country=US --enable-native-access=ALL-UNNAMED"
mkdir -p %{_builddir}/tmp
export TMPDIR=%{_builddir}/tmp

# Ghidra rejects Gradle below 9.1. Check before the C++ builds.
gradle --no-daemon --version | grep -E -q 'Gradle 9\.'
# Ninja defaults to every core. Keep the three C++ trees at the same width
# as the Gradle worker cap.
export CMAKE_BUILD_PARALLEL_LEVEL=8

case "%{_arch}" in
aarch64)
	ghidra_os=linux_arm_64
	;;
x86_64|znver1)
	ghidra_os=linux_x86_64
	;;
*)
	echo "Ghidra has no platform directory for %{_arch}" >&2
	exit 1
	;;
esac

cmake -S %{_builddir}/abseil-cpp-20250127.0 -B %{_builddir}/abseil-build -G Ninja \
	-DCMAKE_BUILD_TYPE=Release \
	-DCMAKE_INSTALL_PREFIX=%{_builddir}/protoc-root \
	-DCMAKE_C_COMPILER=clang \
	-DCMAKE_CXX_COMPILER=clang++ \
	-DCMAKE_CXX_STANDARD=17 \
	-DABSL_BUILD_TESTING=OFF \
	-DABSL_PROPAGATE_CXX_STD=ON \
	-DABSL_ENABLE_INSTALL=ON \
	-DBUILD_SHARED_LIBS=OFF
cmake --build %{_builddir}/abseil-build
cmake --install %{_builddir}/abseil-build

cmake -S %{_builddir}/protobuf-31.0 -B %{_builddir}/protobuf-build -G Ninja \
	-DCMAKE_BUILD_TYPE=Release \
	-DCMAKE_INSTALL_PREFIX=%{_builddir}/protoc-root \
	-DCMAKE_PREFIX_PATH=%{_builddir}/protoc-root \
	-DCMAKE_C_COMPILER=clang \
	-DCMAKE_CXX_COMPILER=clang++ \
	-Dprotobuf_BUILD_TESTS=OFF \
	-Dprotobuf_BUILD_CONFORMANCE=OFF \
	-Dprotobuf_BUILD_EXAMPLES=OFF \
	-Dprotobuf_BUILD_LIBUPB=ON \
	-Dprotobuf_BUILD_SHARED_LIBS=OFF \
	-DBUILD_SHARED_LIBS=OFF \
	-Dprotobuf_LOCAL_DEPENDENCIES_ONLY=ON \
	-Dprotobuf_INSTALL=ON \
	-Dprotobuf_WITH_ZLIB=ON
cmake --build %{_builddir}/protobuf-build --target protoc
mkdir -p %{_builddir}/protoc-root/bin
cp -a %{_builddir}/protobuf-build/protoc-31.0.0 %{_builddir}/protoc-root/bin/protoc
%{_builddir}/protoc-root/bin/protoc --version | grep -q 'libprotoc 31\.'

cmake -S %{_builddir}/z3-z3-4.13.3 -B %{_builddir}/z3-build -G Ninja \
	-DCMAKE_BUILD_TYPE=Release \
	-DCMAKE_C_COMPILER=clang \
	-DCMAKE_CXX_COMPILER=clang++ \
	-DCMAKE_SKIP_RPATH=ON \
	-DZ3_BUILD_JAVA_BINDINGS=ON \
	-DZ3_BUILD_LIBZ3_SHARED=ON \
	-DZ3_ENABLE_EXAMPLE_TARGETS=OFF \
	-DZ3_BUILD_DOCUMENTATION=OFF \
	-DZ3_INCLUDE_GIT_HASH=OFF \
	-DZ3_INCLUDE_GIT_DESCRIBE=OFF
cmake --build %{_builddir}/z3-build --target z3java --target z3JavaJar

jni=$(find %{_builddir}/z3-build -name libz3java.so -type f | head -1)
jar=$(find %{_builddir}/z3-build -name com.microsoft.z3.jar -type f | head -1)
test -n "$jni"
test -n "$jar"
if readelf -d "$jni" | grep -qE 'RPATH|RUNPATH'; then
	patchelf --remove-rpath "$jni"
fi
if readelf -d "$jni" | grep -qE 'RPATH|RUNPATH'; then
	echo "libz3java.so still has an rpath" >&2
	exit 1
fi
needed=$(readelf -d "$jni" | awk '/NEEDED/ && /libz3\.so/ { gsub(/[][]/, "", $NF); print $NF }')
test "$needed" = "libz3.so.4.13"

rm -rf dependencies/SymbolicSummaryZ3
mkdir -p "dependencies/SymbolicSummaryZ3/os/${ghidra_os}" "dependencies/flatRepo"
cp -a "$jni" "dependencies/SymbolicSummaryZ3/os/${ghidra_os}/libz3java.so"
cp -a "$jar" dependencies/flatRepo/com.microsoft.z3.jar
test ! -e "dependencies/SymbolicSummaryZ3/os/${ghidra_os}/libz3.so"

gradle --offline --no-daemon --parallel --max-workers=8 \
	-PprotocPath=%{_builddir}/protoc-root/bin/protoc \
	buildGhidra

mkdir -p %{_builddir}/ghidra-wheels/jpype %{_builddir}/ghidra-wheels/psutil
python -m pip wheel --no-deps --no-index --no-build-isolation \
	-w %{_builddir}/ghidra-wheels/jpype \
	dependencies/PyGhidra/jpype1-1.5.2.tar.gz
python -m pip wheel --no-deps --no-index --no-build-isolation \
	-w %{_builddir}/ghidra-wheels/psutil \
	dependencies/Debugger-rmi-trace/psutil-5.9.8.tar.gz

python - << 'PY'
import glob, io, sys, zipfile
outer = glob.glob("build/dist/ghidra_%{version}_PUBLIC_*.zip")
if len(outer) != 1:
    sys.exit("expected one installation zip, found " + repr(outer))
with zipfile.ZipFile(outer[0]) as zipped:
    nested = [name for name in zipped.namelist() if name.endswith("SymbolicSummaryZ3.zip")]
    if len(nested) != 1:
        sys.exit("expected one SymbolicSummaryZ3 zip, found " + repr(nested))
    payload = zipped.read(nested[0])
with zipfile.ZipFile(io.BytesIO(payload)) as inner:
    names = inner.namelist()
bad = [name for name in names if name.endswith(("/libz3.so", "/libz3.dylib", "/libz3.dll"))]
if bad:
    sys.exit("refusing to ship a bundled libz3: " + " ".join(bad))
jni_names = [name for name in names if "libz3java" in name]
if len(jni_names) != 1:
    sys.exit("expected one libz3java in the extension, found " + repr(jni_names))
PY

%install
rm -rf %{buildroot}
cd %{_builddir}/ghidra-Ghidra_%{version}_build
mkdir -p %{buildroot}%{_datadir}
unzip -q -d %{buildroot}%{_datadir} build/dist/ghidra_%{version}_PUBLIC_*.zip
mv %{buildroot}%{_datadir}/ghidra_%{version}_PUBLIC %{buildroot}%{_datadir}/ghidra

cp -a %{_builddir}/ghidra-wheels/jpype/jpype1-*.whl \
	%{buildroot}%{_datadir}/ghidra/Ghidra/Features/PyGhidra/pypkg/dist/
cp -a %{_builddir}/ghidra-wheels/psutil/psutil-*.whl \
	%{buildroot}%{_datadir}/ghidra/Ghidra/Debug/Debugger-rmi-trace/pypkg/dist/

mkdir -p %{buildroot}%{_bindir}
ln -s ../share/ghidra/ghidraRun %{buildroot}%{_bindir}/ghidra
ln -s ../share/ghidra/support/pyghidraRun %{buildroot}%{_bindir}/pyghidra
ln -s ../share/ghidra/support/analyzeHeadless %{buildroot}%{_bindir}/analyzeHeadless
ln -s ../share/ghidra/support/bsim %{buildroot}%{_bindir}/bsim
ln -s ../share/ghidra/support/bsim_ctl %{buildroot}%{_bindir}/bsim_ctl
ln -s ../share/ghidra/support/sleigh %{buildroot}%{_bindir}/sleigh
ln -s ../share/ghidra/server/ghidraSvr %{buildroot}%{_bindir}/ghidraSvr

mkdir -p %{buildroot}%{_datadir}/applications
cat > %{buildroot}%{_datadir}/applications/ghidra.desktop << 'EOF'
[Desktop Entry]
Name=Ghidra
GenericName=Software Reverse Engineering Suite
Comment=Disassemble and decompile native programs
Exec=ghidra
Icon=ghidra
Terminal=false
Type=Application
Categories=Development;Debugger;
Keywords=disassembler;decompiler;reverse engineering;
StartupWMClass=ghidra-Ghidra
EOF

for size in 16 24 32 40 48 64 128 256; do
	install -D -m 644 \
		Ghidra/Framework/Gui/src/main/resources/images/GhidraIcon${size}.png \
		%{buildroot}%{_iconsdir}/hicolor/${size}x${size}/apps/ghidra.png
done

%files
%license LICENSE
%doc README.md NOTICE
%{_bindir}/ghidra
%{_bindir}/pyghidra
%{_bindir}/analyzeHeadless
%{_bindir}/bsim
%{_bindir}/bsim_ctl
%{_bindir}/sleigh
%{_bindir}/ghidraSvr
%{_datadir}/applications/ghidra.desktop
%{_iconsdir}/hicolor/*/apps/ghidra.png
%{_datadir}/ghidra
