fn main() {
    println!("cargo:rerun-if-changed=assets/app-icon.ico");

    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() != Ok("windows") {
        return;
    }

    let icon = "assets/app-icon.ico";
    if !std::path::Path::new(icon).exists() {
        return;
    }

    let mut resource = winresource::WindowsResource::new();
    resource.set("FileDescription", "NETIX Simulator");
    resource.set("ProductName", "NETIX Simulator");
    resource.set("CompanyName", "NETIX");
    resource.set_icon(icon);
    resource
        .compile()
        .expect("failed to compile Windows executable resources");
}
