function confirmDelete(event, message) {
    event.preventDefault();
    const form = event.currentTarget;
    Swal.fire({
        title: message || "ยืนยันการลบ?",
        icon: "warning",
        showCancelButton: true,
        confirmButtonText: "ยืนยัน",
        cancelButtonText: "ยกเลิก"
    }).then(result => {
        if (result.isConfirmed) form.submit();
    });
    return false;
}
document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".alert").forEach(el => {
        setTimeout(() => {
            const alert = bootstrap.Alert.getOrCreateInstance(el);
            alert.close();
        }, 4500);
    });
});
