"""Generate a small native Xcode project without a project-generator dependency."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parent
objects = {}

def ident(name):
    return hashlib.sha256(name.encode()).hexdigest()[:24].upper()

def obj(key_name, isa, **properties):
    key = ident(key_name)
    objects[key] = dict(isa=isa, **properties)
    return key

def value(v):
    if isinstance(v, dict):
        return '{ ' + ' '.join(f'{json.dumps(k)} = {value(x)};' for k, x in v.items()) + ' }'
    if isinstance(v, list):
        return '( ' + ', '.join(value(x) for x in v) + ' )'
    return json.dumps(str(v))

shared = ['Shared/Models.swift', 'Shared/Cache.swift', 'Shared/Appearance.swift', 'Shared/GlucoseChart.swift']
files = shared + ['App/ConnectionStore.swift', 'App/ProcessLock.swift', 'App/SingleInstance.swift', 'App/AppModel.swift', 'App/StatusBadge.swift', 'App/Views.swift', 'App/Main.swift', 'Widget/GlucoseWidget.swift', 'Widget/RemoteDashboard.swift']
refs = {name: obj('ref:'+name, 'PBXFileReference', lastKnownFileType='sourcecode.swift', path=name, sourceTree='<group>') for name in files}
icon_ref = obj('icon', 'PBXFileReference', lastKnownFileType='image.icns', path='App/OttaiMirror.icns', sourceTree='<group>')
app_product = obj('product:app', 'PBXFileReference', explicitFileType='wrapper.application', path='OttaiMirror.app', sourceTree='BUILT_PRODUCTS_DIR')
widget_product = obj('product:widget', 'PBXFileReference', explicitFileType='wrapper.app-extension', path='OttaiGlucoseWidget.appex', sourceTree='BUILT_PRODUCTS_DIR')
products = obj('products', 'PBXGroup', children=[app_product, widget_product], name='Products', sourceTree='<group>')
group = obj('group', 'PBXGroup', children=list(refs.values())+[icon_ref, products], sourceTree='<group>')

common = dict(MACOSX_DEPLOYMENT_TARGET='15.0', SDKROOT='macosx', SWIFT_VERSION='5.0', CLANG_ENABLE_MODULES='YES',
              CODE_SIGN_IDENTITY='-', CODE_SIGN_STYLE='Manual', ENABLE_HARDENED_RUNTIME='YES',
              SWIFT_EMIT_LOC_STRINGS='NO', GENERATE_INFOPLIST_FILE='NO')

def configs(name, settings):
    result = []
    for configuration in ['Debug', 'Release']:
        conf = dict(common, **settings)
        conf['SWIFT_OPTIMIZATION_LEVEL'] = '-O' if configuration == 'Release' else '-Onone'
        result.append(obj(name+configuration, 'XCBuildConfiguration', buildSettings=conf, name=configuration))
    return obj(name+'configs', 'XCConfigurationList', buildConfigurations=result, defaultConfigurationIsVisible=0, defaultConfigurationName='Release')

widget_sources = obj('widget sources', 'PBXSourcesBuildPhase', buildActionMask=2147483647,
                     files=[obj('widget build:'+name, 'PBXBuildFile', fileRef=refs[name]) for name in shared+['Widget/GlucoseWidget.swift', 'Widget/RemoteDashboard.swift']], runOnlyForDeploymentPostprocessing=0)
widget_target = obj('widget target', 'PBXNativeTarget', name='OttaiGlucoseWidget', productName='OttaiGlucoseWidget',
                    productReference=widget_product, productType='com.apple.product-type.app-extension', buildPhases=[widget_sources],
                    buildRules=[], dependencies=[], buildConfigurationList=configs('widget', dict(PRODUCT_NAME='OttaiGlucoseWidget',
                    PRODUCT_BUNDLE_IDENTIFIER='com.joviliu.ottai.mirror.widget', INFOPLIST_FILE='Widget/Info.plist',
                    CODE_SIGN_ENTITLEMENTS='Widget/Widget.entitlements', SKIP_INSTALL='YES', APPLICATION_EXTENSION_API_ONLY='YES')))
proxy = obj('widget proxy', 'PBXContainerItemProxy', containerPortal=ident('project'), proxyType=1, remoteGlobalIDString=widget_target, remoteInfo='OttaiGlucoseWidget')
dependency = obj('widget dependency', 'PBXTargetDependency', target=widget_target, targetProxy=proxy)
embedded = obj('embed widget', 'PBXCopyFilesBuildPhase', buildActionMask=2147483647, dstPath='', dstSubfolderSpec=13,
               files=[obj('embed widget build', 'PBXBuildFile', fileRef=widget_product, settings={'ATTRIBUTES': ['RemoveHeadersOnCopy']})],
               name='Embed App Extensions', runOnlyForDeploymentPostprocessing=0)
resources = obj('app resources', 'PBXResourcesBuildPhase', buildActionMask=2147483647,
                files=[obj('icon build', 'PBXBuildFile', fileRef=icon_ref)], runOnlyForDeploymentPostprocessing=0)
app_sources = obj('app sources', 'PBXSourcesBuildPhase', buildActionMask=2147483647,
                  files=[obj('app build:'+name, 'PBXBuildFile', fileRef=refs[name]) for name in shared+['App/ConnectionStore.swift', 'App/ProcessLock.swift', 'App/SingleInstance.swift', 'App/AppModel.swift', 'App/StatusBadge.swift', 'App/Views.swift', 'App/Main.swift']], runOnlyForDeploymentPostprocessing=0)
app_target = obj('app target', 'PBXNativeTarget', name='OttaiMirror', productName='OttaiMirror', productReference=app_product,
                 productType='com.apple.product-type.application', buildPhases=[app_sources, resources, embedded], buildRules=[], dependencies=[dependency],
                 buildConfigurationList=configs('app', dict(PRODUCT_NAME='OttaiMirror', PRODUCT_BUNDLE_IDENTIFIER='com.joviliu.ottai.mirror',
                 INFOPLIST_FILE='App/Info.plist', CODE_SIGN_ENTITLEMENTS='App/App.entitlements')))
project = obj('project', 'PBXProject', attributes={'LastUpgradeCheck': '1630'}, buildConfigurationList=configs('project', {}),
              compatibilityVersion='Xcode 14.0', developmentRegion='zh-Hans', knownRegions=['zh-Hans', 'en'], mainGroup=group,
              productRefGroup=products, projectDirPath='', projectRoot='', targets=[app_target, widget_target])
directory = root/'OttaiMirror.xcodeproj'
directory.mkdir(exist_ok=True)
(directory/'project.pbxproj').write_text('// !$*UTF8*$!\n' + value(dict(archiveVersion=1, classes={}, objectVersion=56, objects=objects, rootObject=project)) + '\n')
scheme = directory/'xcshareddata/xcschemes'
scheme.mkdir(parents=True, exist_ok=True)
(scheme/'OttaiMirror.xcscheme').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="1630" version="1.3">
 <BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries>
 <BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">
 <BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{app_target}" BuildableName="OttaiMirror.app" BlueprintName="OttaiMirror" ReferencedContainer="container:OttaiMirror.xcodeproj"/>
 </BuildActionEntry></BuildActionEntries></BuildAction>
 <LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" debugServiceExtension="internal" allowLocationSimulation="NO">
 <BuildableProductRunnable runnableDebuggingMode="0"><BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{app_target}" BuildableName="OttaiMirror.app" BlueprintName="OttaiMirror" ReferencedContainer="container:OttaiMirror.xcodeproj"/></BuildableProductRunnable>
 </LaunchAction><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>
''')
print('Generated OttaiMirror.xcodeproj')
